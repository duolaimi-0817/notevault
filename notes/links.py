"""
笔记双向链接（[[标题]]）的解析、同步与读取侧统计。

解析规则（与需求逐条对应）：
- 只在同一用户的笔记范围内解析目标，绝不链接到别人的笔记；
- 同一用户下标题重复时，取 create_at 最早的那一条；
- 指向自己的链接忽略（最早的一条恰好是自己时，不回退到同名次新笔记）；
- 同一正文里同一目标出现多次，只建立一条关系；
- 行内代码 `...` 与围栏代码块 ```...``` / ~~~...~~~ 内的 [[...]] 不算链接；
- 目标标题不存在时不报错、不建关系，未解析标题通过 sync_note_links 的返回值告知调用方；
- 目标在回收站（is_deleted=True）时关系照常建立/保留，“失效”状态不在本表存标记位，
  读取时由 target/source 的 is_deleted 派生（backlink_count 只计未软删的引用方）。
"""
import re

from django.db.models import Count, IntegerField, OuterRef, Subquery
from django.db.models.functions import Coalesce

from .models import Note, NoteLink

# [[标题]]：标题内不允许出现方括号或换行，避免跨行误匹配
_WIKI_LINK_RE = re.compile(r'\[\[([^\[\]\n]+?)\]\]')
# 围栏代码块开头：行首至多 3 个空格，随后至少 3 个反引号或波浪号
_FENCE_RE = re.compile(r'^ {0,3}(`{3,}|~{3,})')


def _remove_inline_code(line):
    """
    去掉一行内的行内代码片段。支持单反引号 `code` 与双反引号 ``a ` b`` 定界；
    找不到闭合定界符时，反引号按普通字符处理（CommonMark 同样不把它视为代码）。
    """
    out = []
    i = 0
    length = len(line)
    while i < length:
        if line[i] == '`':
            j = i + 1
            while j < length and line[j] == '`':
                j += 1
            delimiter = line[i:j]
            close = line.find(delimiter, j)
            if close == -1:
                out.append(line[i:])
                break
            # 代码内容整体丢弃，i 直接跳到闭合定界符之后
            i = close + len(delimiter)
        else:
            out.append(line[i])
            i += 1
    return ''.join(out)


def extract_link_titles(content):
    """
    从 Markdown 正文中按出现顺序提取 [[标题]] 里的原始标题文本（不去重）。
    逐行扫描：围栏代码块内的行整体跳过；普通行先剔除行内代码再匹配。
    """
    titles = []
    fence_char = None  # None 表示不在围栏内；否则为 '`' 或 '~'
    for line in content.splitlines():
        if fence_char is not None:
            stripped = line.strip()
            # 闭合围栏：同种字符、至少 3 个，且该行只有这一串符号
            if len(stripped) >= 3 and stripped[0] == fence_char and set(stripped) == {fence_char}:
                fence_char = None
            continue
        fence_match = _FENCE_RE.match(line)
        if fence_match:
            fence_char = fence_match.group(1)[0]
            continue
        cleaned_line = _remove_inline_code(line)
        for match in _WIKI_LINK_RE.finditer(cleaned_line):
            title = match.group(1).strip()
            if title:
                titles.append(title)
    return titles


def sync_note_links(note):
    """
    根据 note.content 重新解析并全量重建该笔记的出链关系。
    只应在“保存这条笔记的正文”时调用。

    返回：
    {
        'resolved_count': 成功建立关系的目标数,
        'unresolved_link_count': 解析不出的去重标题数,
        'unresolved_link_titles': 解析不出的原始标题文本（去重、保序）,
    }
    """
    raw_titles = extract_link_titles(note.content or '')
    # 同一目标出现多次只建一条：先按出现顺序去重
    unique_titles = list(dict.fromkeys(raw_titles))

    earliest_by_title = {}
    if unique_titles:
        # 包含软删笔记：目标在回收站时关系仍要保留
        candidates = (
            Note.all_objects.filter(owner_id=note.owner_id, title__in=unique_titles)
            .only('id', 'title', 'create_at')
            .order_by('create_at', 'id')
        )
        for candidate in candidates:
            if candidate.title not in earliest_by_title:
                earliest_by_title[candidate.title] = candidate

    target_ids = []
    unresolved_titles = []
    for title in unique_titles:
        target = earliest_by_title.get(title)
        if target is None:
            unresolved_titles.append(title)
            continue
        if target.id == note.id:
            # 指向自己：忽略，不计入未解析
            continue
        target_ids.append(target.id)

    # 全量替换：旧关系先删后建（unique_together 下也能处理“本次删掉的链接”）
    NoteLink.objects.filter(source=note).delete()
    if target_ids:
        NoteLink.objects.bulk_create(
            [NoteLink(source_id=note.id, target_id=tid) for tid in target_ids]
        )

    return {
        'resolved_count': len(target_ids),
        'unresolved_link_count': len(unresolved_titles),
        'unresolved_link_titles': unresolved_titles,
    }


def with_link_counts(queryset):
    """
    给笔记 queryset 追加两个只读统计字段（用相关子查询实现，查询数恒定、无 N+1）：
    - link_count：出链关系总数（含目标已软删的关系——关系在回收站期间仍然保留）；
    - backlink_count：被多少条“未软删”的笔记引用。
    """
    outgoing_subquery = Subquery(
        NoteLink.objects.filter(source=OuterRef('pk'))
        .values('source')
        .annotate(c=Count('id'))
        .values('c'),
        output_field=IntegerField(),
    )
    backlink_subquery = Subquery(
        NoteLink.objects.filter(target=OuterRef('pk'), source__is_deleted=False)
        .values('target')
        .annotate(c=Count('id'))
        .values('c'),
        output_field=IntegerField(),
    )
    return queryset.annotate(
        link_count=Coalesce(outgoing_subquery, 0),
        backlink_count=Coalesce(backlink_subquery, 0),
    )
