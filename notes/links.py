"""
笔记双向链接 [[标题]] 的解析、关系同步与读取侧统计。

规则（与需求逐条对应）：
- 只解析笔记作者本人名下的标题，跨用户永不解析（resolve_target_titles 按 owner 过滤）。
- 同一用户下标题重复时，取 create_at 最早的一条（id 作并列兜底）。
- 指向自己的链接忽略（sync_note_links 跳过 target.id == source.id）。
- 同一正文里同一目标出现多次，只保留一条（extract_link_titles 去重）。
- 行内代码 `...` 与围栏代码块 ```...``` 内的 [[...]] 不解析，纯手写、无第三方依赖。
- 标题在本用户下不存在：不建关系，原始标题写入 note.broken_link_titles 供接口返回。
- 目标在回收站：关系保留；失效状态由 source/target 的 is_deleted 推导，恢复自动生效。

解析只在「保存这条笔记」时由 sync_note_links 触发。
"""
import re

from django.db.models import Count, Q

from .models import Note, NoteLink

# 围栏代码块开围栏：0-3 个空格缩进 + 至少 3 个反引号，后面可跟 info string
_FENCE_OPEN_RE = re.compile(r'^ {0,3}(`{3,})(.*)$')
# 围栏代码块闭围栏：0-3 个空格缩进 + 不少于开围栏长度的反引号，行尾只允许空白
_FENCE_CLOSE_RE = re.compile(r'^ {0,3}(`{3,})[ \t]*$')


def _run_length(text, index, char):
    """返回 text[index:] 起始处连续 char 的个数。"""
    length = 0
    while index + length < len(text) and text[index + length] == char:
        length += 1
    return length


def _find_backtick_run(text, start, run_len):
    """
    从 start 开始寻找长度恰好等于 run_len 的反引号串（代码段闭合规则）。
    找到返回起始下标，否则返回 -1。
    """
    index = start
    while index < len(text):
        if text[index] == '`':
            length = _run_length(text, index, '`')
            if length == run_len:
                return index
            index += length
        else:
            index += 1
    return -1


def _find_links_outside_code_spans(line):
    """
    扫描单行文本，跳过反引号代码段（支持 `` 等多反引号定界），
    返回其中 [[标题]] 的标题文本列表（保留出现顺序，允许重复；标题去掉首尾空白）。
    标题内部不允许出现方括号，以避免嵌套歧义。
    """
    results = []
    index = 0
    total = len(line)
    while index < total:
        char = line[index]
        if char == '`':
            run_len = _run_length(line, index, '`')
            close = _find_backtick_run(line, index + run_len, run_len)
            if close == -1:
                # 未闭合的反引号按普通文本处理，继续扫描其后内容
                index += run_len
            else:
                index = close + run_len
            continue
        if char == '[' and index + 1 < total and line[index + 1] == '[':
            end = line.find(']]', index + 2)
            if end != -1:
                inner = line[index + 2:end]
                if '[' in inner or ']' in inner:
                    # 内层含方括号，不认作链接，只跳过开头两个括号继续向后扫描
                    index += 2
                    continue
                title = inner.strip()
                if title:
                    results.append(title)
                index = end + 2
                continue
        index += 1
    return results


def extract_link_titles(content):
    """
    从笔记正文中按首次出现顺序抽取 [[标题]] 标题文本。
    围栏代码块整体跳过；行内代码段在逐行扫描时跳过。
    返回去重后的 list[str]。
    """
    ordered = []
    seen = set()
    in_fence = False
    fence_len = 0
    for line in content.splitlines():
        if in_fence:
            close_match = _FENCE_CLOSE_RE.match(line)
            if close_match and len(close_match.group(1)) >= fence_len:
                in_fence = False
            continue
        open_match = _FENCE_OPEN_RE.match(line)
        if open_match:
            in_fence = True
            fence_len = len(open_match.group(1))
            # 开围栏行（含 info string）不参与链接解析
            continue
        for title in _find_links_outside_code_spans(line):
            if title not in seen:
                seen.add(title)
                ordered.append(title)
    return ordered


def resolve_target_titles(owner, titles):
    """
    将标题文本解析为目标笔记。
    只查 owner 本人的笔记，且使用 all_objects 以包含回收站中的笔记；
    标题重复时取 create_at 最早（create_at 相同时 id 较小者）。
    返回 {title: Note}。
    """
    if not titles:
        return {}
    candidates = (
        Note.all_objects.filter(owner=owner, title__in=list(titles))
        .order_by('create_at', 'id')
    )
    resolved = {}
    for note in candidates:
        if note.title not in resolved:
            resolved[note.title] = note
    return resolved


def sync_note_links(note):
    """
    解析 note.content 并与现有 NoteLink 关系对账：
    - 新增缺失关系、删除多余关系（同目标多次出现只建一条，自链接忽略）；
    - 无法解析的原始标题写入 note.broken_link_titles。
    返回 {'unresolved_count': int, 'unresolved_titles': list[str]}。
    """
    titles = extract_link_titles(note.content)
    resolved = resolve_target_titles(note.owner, titles)

    desired_target_ids = set()
    unresolved = []
    for title in titles:
        target = resolved.get(title)
        if target is None:
            unresolved.append(title)
        elif target.id == note.id:
            # 指向自己的链接忽略
            continue
        else:
            desired_target_ids.add(target.id)

    existing_ids = set(
        NoteLink.objects.filter(source=note).values_list('target_id', flat=True)
    )
    if existing_ids - desired_target_ids:
        NoteLink.objects.filter(source=note).exclude(
            target_id__in=desired_target_ids
        ).delete()
    for target_id in desired_target_ids - existing_ids:
        NoteLink.objects.create(source=note, target_id=target_id)

    # 用 update() 只写该字段，避免再触发一次 save()/auto_now
    Note.all_objects.filter(id=note.id).update(broken_link_titles=unresolved)
    note.broken_link_titles = unresolved

    return {'unresolved_count': len(unresolved), 'unresolved_titles': unresolved}


def with_link_counts(queryset):
    """
    给笔记 queryset 增加两个只读统计字段（聚合进同一条查询，杜绝 N+1）：
    - link_count：出链数，仅统计目标未软删的关系；
    - backlink_count：被多少条未软删的笔记引用。
    目标/引用方进入回收站时关系保留但不计入，恢复后自动重新计入。
    """
    return queryset.annotate(
        link_count=Count(
            'outgoing_links',
            filter=Q(outgoing_links__target__is_deleted=False),
            distinct=True,
        ),
        backlink_count=Count(
            'incoming_links',
            filter=Q(incoming_links__source__is_deleted=False),
            distinct=True,
        ),
    )
