from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from django.core.files.uploadedfile import SimpleUploadedFile

from notes.models import User, Note, NoteLink


def make_user(phone):
    return User.objects.create_user(phone=phone, password='password123')


def make_note(owner, title, content=''):
    return Note.objects.create(owner=owner, title=title, content=content)


def auth_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def backdate(note_id, days):
    """把笔记 create_at 往前拨 days 天（绕过 auto_now_add）。"""
    Note.all_objects.filter(id=note_id).update(
        create_at=timezone.now() - timedelta(days=days)
    )


class NoteLinkTests(TestCase):
    """双向链接 [[标题]] 与反向引用。"""

    # ---------- 正常建链 ----------
    def test_create_link_normal(self):
        user = make_user('13800000001')
        target = make_note(user, '目标')

        client = auth_client(user)
        resp = client.post('/api/notes/', {'title': '来源', 'content': '参见 [[目标]]'}, format='json')
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data['link_count'], 1)
        self.assertEqual(resp.data['backlink_count'], 0)
        self.assertEqual(resp.data['unresolved_link_count'], 0)
        self.assertEqual(resp.data['unresolved_link_titles'], [])

        # 目标详情：被 1 条未软删笔记引用
        detail = client.get(f'/api/notes/{target.id}/')
        self.assertEqual(detail.data['backlink_count'], 1)
        self.assertEqual(detail.data['link_count'], 0)

        # 反向引用列表
        backlinks = client.get(f'/api/notes/{target.id}/backlinks/')
        self.assertEqual(backlinks.status_code, 200)
        self.assertEqual(len(backlinks.data), 1)
        item = backlinks.data[0]
        self.assertEqual(item['title'], '来源')
        self.assertFalse(item['is_deleted'])
        self.assertFalse(item['is_pinned'])
        self.assertIn('create_at', item)

        self.assertEqual(NoteLink.objects.count(), 1)

    # ---------- 同标题重复：取 create_at 最早 ----------
    def test_duplicate_titles_resolve_earliest(self):
        user = make_user('13800000002')
        earlier = make_note(user, '重复标题')
        later = make_note(user, '重复标题')
        backdate(earlier.id, 2)
        backdate(later.id, 1)

        client = auth_client(user)
        client.post('/api/notes/', {'title': '来源', 'content': '[[重复标题]]'}, format='json')

        link = NoteLink.objects.get()
        self.assertEqual(link.target_id, earlier.id)

    # ---------- 跨用户隔离 ----------
    def test_cross_user_isolation(self):
        user1 = make_user('13800000003')
        user2 = make_user('13800000004')
        other_note = make_note(user2, '目标')

        client1 = auth_client(user1)
        # user1 没有自己的「目标」，同名的是 user2 的笔记：必须算无法解析，不能链接过去
        resp = client1.post('/api/notes/', {'title': '来源', 'content': '[[目标]]'}, format='json')
        self.assertEqual(resp.data['unresolved_link_count'], 1)
        self.assertEqual(resp.data['unresolved_link_titles'], ['目标'])
        self.assertEqual(resp.data['link_count'], 0)
        self.assertEqual(NoteLink.objects.count(), 0)

        # user1 后来创建自己的「目标」，重新保存来源后只解析到自己的
        own_note = client1.post('/api/notes/', {'title': '目标', 'content': '我的'}, format='json')
        source_id = resp.data['id']
        updated = client1.put(f'/api/notes/{source_id}/', {'title': '来源', 'content': '[[目标]]'}, format='json')
        self.assertEqual(updated.data['link_count'], 1)
        self.assertEqual(updated.data['unresolved_link_count'], 0)
        link = NoteLink.objects.get(source_id=source_id)
        self.assertEqual(link.target_id, own_note.data['id'])
        self.assertNotEqual(link.target_id, other_note.id)

        # user2 视角没有任何入链
        client2 = auth_client(user2)
        detail2 = client2.get(f'/api/notes/{other_note.id}/')
        self.assertEqual(detail2.data['backlink_count'], 0)

    # ---------- 自链接忽略 ----------
    def test_self_link_ignored(self):
        user = make_user('13800000005')
        client = auth_client(user)
        resp = client.post('/api/notes/', {'title': '自述', 'content': '[[自述]]'}, format='json')
        self.assertEqual(resp.data['link_count'], 0)
        self.assertEqual(resp.data['unresolved_link_count'], 0)
        self.assertEqual(NoteLink.objects.count(), 0)

    # ---------- 行内代码 / 围栏代码块内的链接不算 ----------
    def test_links_inside_code_ignored(self):
        user = make_user('13800000006')
        make_note(user, '目标')
        client = auth_client(user)

        content = (
            '行内代码 `[[目标]]` 不算链接\n'
            '围栏代码块：\n'
            '```python\n'
            'print("[[目标]]")\n'
            '```\n'
            '结尾'
        )
        resp = client.post('/api/notes/', {'title': '来源', 'content': content}, format='json')
        self.assertEqual(resp.data['link_count'], 0)
        self.assertEqual(NoteLink.objects.count(), 0)

        # 代码块外出现同样的标题文本则正常建链
        updated = client.put(
            f'/api/notes/{resp.data["id"]}/',
            {'title': '来源', 'content': content + '\n真正引用 [[目标]]'},
            format='json',
        )
        self.assertEqual(updated.data['link_count'], 1)
        self.assertEqual(NoteLink.objects.count(), 1)

    # ---------- 无法解析链接：去重、保序，建目标后重存即生效 ----------
    def test_unresolved_links_dedupe_order_and_resolve(self):
        user = make_user('13800000007')
        client = auth_client(user)

        resp = client.post(
            '/api/notes/',
            {'title': '来源', 'content': '[[幽灵乙]] [[幽灵甲]] [[幽灵乙]]'},
            format='json',
        )
        self.assertEqual(resp.data['unresolved_link_count'], 2)
        self.assertEqual(resp.data['unresolved_link_titles'], ['幽灵乙', '幽灵甲'])

        # 创建其中一个目标后重新保存来源（content 不允许空串）
        client.post('/api/notes/', {'title': '幽灵甲', 'content': '内容'}, format='json')
        updated = client.put(
            f'/api/notes/{resp.data["id"]}/',
            {'title': '来源', 'content': '[[幽灵乙]] [[幽灵甲]]'},
            format='json',
        )
        self.assertEqual(updated.data['link_count'], 1)
        self.assertEqual(updated.data['unresolved_link_count'], 1)
        self.assertEqual(updated.data['unresolved_link_titles'], ['幽灵乙'])

    # ---------- 目标在回收站：关系保留、标记失效，restore 后重新生效 ----------
    def test_target_in_recycle_bin_invalid_then_restore(self):
        user = make_user('13800000008')
        target = make_note(user, '目标')
        client = auth_client(user)
        source = client.post('/api/notes/', {'title': '来源', 'content': '[[目标]]'}, format='json')

        # 软删目标
        self.assertEqual(client.delete(f'/api/notes/{target.id}/').status_code, 200)

        # 关系行保留
        self.assertEqual(NoteLink.objects.filter(source_id=source.data['id']).count(), 1)
        # 出链失效：link_count 不计入回收站目标
        detail = client.get(f'/api/notes/{source.data["id"]}/')
        self.assertEqual(detail.data['link_count'], 0)

        # 对已软删的本人目标查反向引用：来源仍出现
        backlinks = client.get(f'/api/notes/{target.id}/backlinks/')
        self.assertEqual(backlinks.status_code, 200)
        self.assertEqual(len(backlinks.data), 1)
        self.assertEqual(backlinks.data[0]['id'], source.data['id'])

        # restore 目标后关系自动重新生效
        restored = client.post('/api/recycle-bin/', {'action': 'restore', 'note_id': target.id}, format='json')
        self.assertEqual(restored.status_code, 200)
        detail = client.get(f'/api/notes/{source.data["id"]}/')
        self.assertEqual(detail.data['link_count'], 1)

    # ---------- 来源被单条软删：入链计数随之变化，restore 后恢复 ----------
    def test_source_soft_delete_then_restore(self):
        user = make_user('13800000009')
        target = make_note(user, '目标')
        client = auth_client(user)
        source = client.post('/api/notes/', {'title': '来源', 'content': '[[目标]]'}, format='json')

        client.delete(f'/api/notes/{source.data["id"]}/')
        self.assertEqual(client.get(f'/api/notes/{target.id}/').data['backlink_count'], 0)
        # 关系行仍然保留
        self.assertEqual(NoteLink.objects.count(), 1)

        client.post('/api/recycle-bin/', {'action': 'restore', 'note_id': source.data['id']}, format='json')
        self.assertEqual(client.get(f'/api/notes/{target.id}/').data['backlink_count'], 1)

    # ---------- 批量删除（queryset.update，不走 save）backlink_count 仍正确 ----------
    def test_batch_delete_backlink_count_and_deleted_referrer(self):
        user = make_user('13800000010')
        target = make_note(user, '目标')
        client = auth_client(user)
        s1 = client.post('/api/notes/', {'title': '来源一', 'content': '[[目标]]'}, format='json')
        s2 = client.post('/api/notes/', {'title': '来源二', 'content': '[[目标]]'}, format='json')
        self.assertEqual(client.get(f'/api/notes/{target.id}/').data['backlink_count'], 2)

        # 批量软删：queryset.update()，不触发 save/信号；统计由读取侧注解实时推导
        resp = client.post(
            '/api/notes/batch/',
            {'action': 'delete', 'note_ids': [s1.data['id'], s2.data['id']]},
            format='json',
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(client.get(f'/api/notes/{target.id}/').data['backlink_count'], 0)

        # 反向引用列表里已软删的引用方仍出现并带 is_deleted=true
        backlinks = client.get(f'/api/notes/{target.id}/backlinks/')
        self.assertEqual(len(backlinks.data), 2)
        self.assertTrue(all(item['is_deleted'] for item in backlinks.data))

        # 恢复其中一条：计数回到 1；批量 pin/unpin 不影响链接关系
        client.post('/api/recycle-bin/', {'action': 'restore', 'note_id': s1.data['id']}, format='json')
        self.assertEqual(client.get(f'/api/notes/{target.id}/').data['backlink_count'], 1)
        client.post('/api/notes/batch/', {'action': 'pin', 'note_ids': [s1.data['id']]}, format='json')
        self.assertEqual(client.get(f'/api/notes/{target.id}/').data['backlink_count'], 1)
        client.post('/api/notes/batch/', {'action': 'unpin', 'note_ids': [s1.data['id']]}, format='json')
        self.assertEqual(client.get(f'/api/notes/{target.id}/').data['backlink_count'], 1)

    # ---------- 彻底删除目标：关系随 CASCADE 消失 ----------
    def test_hard_delete_target_cascades_links(self):
        user = make_user('13800000011')
        target = make_note(user, '目标')
        client = auth_client(user)
        s1 = client.post('/api/notes/', {'title': '来源一', 'content': '[[目标]]'}, format='json')
        s2 = client.post('/api/notes/', {'title': '来源二', 'content': '[[目标]]'}, format='json')

        client.delete(f'/api/notes/{target.id}/')
        resp = client.post('/api/recycle-bin/', {'action': 'delete', 'note_id': target.id}, format='json')
        self.assertEqual(resp.status_code, 204)

        self.assertEqual(NoteLink.objects.count(), 0)
        # 来源笔记本身仍在
        self.assertTrue(Note.objects.filter(id=s1.data['id']).exists())
        self.assertTrue(Note.objects.filter(id=s2.data['id']).exists())
        # 目标彻底消失：反向引用接口 404
        self.assertEqual(client.get(f'/api/notes/{target.id}/backlinks/').status_code, 404)

    # ---------- 导入 .md：写入口同样建链 ----------
    def test_import_creates_links(self):
        user = make_user('13800000012')
        target = make_note(user, '目标')
        client = auth_client(user)

        upload = SimpleUploadedFile('导入笔记.md', '正文 [[目标]]'.encode('utf-8'), content_type='text/markdown')
        resp = client.post('/api/notes/import/', {'file': upload}, format='multipart')
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data['title'], '导入笔记')
        self.assertEqual(resp.data['link_count'], 1)
        self.assertEqual(client.get(f'/api/notes/{target.id}/').data['backlink_count'], 1)

    # ---------- 反向引用排序：-is_pinned、-create_at ----------
    def test_backlinks_ordering(self):
        user = make_user('13800000013')
        target = make_note(user, '目标')
        client = auth_client(user)

        old_normal = client.post('/api/notes/', {'title': '旧普通', 'content': '[[目标]]'}, format='json')
        pinned = client.post('/api/notes/', {'title': '置顶', 'content': '[[目标]]'}, format='json')
        recent_normal = client.post('/api/notes/', {'title': '新普通', 'content': '[[目标]]'}, format='json')

        backdate(old_normal.data['id'], 3)
        backdate(pinned.data['id'], 2)
        # recent_normal 保持最新创建时间
        Note.all_objects.filter(id=pinned.data['id']).update(is_pinned=True)

        backlinks = client.get(f'/api/notes/{target.id}/backlinks/')
        ordered_ids = [item['id'] for item in backlinks.data]
        self.assertEqual(ordered_ids, [pinned.data['id'], recent_normal.data['id'], old_normal.data['id']])

    # ---------- backlinks 接口 404：不存在 / 越权 / 未登录 ----------
    def test_backlinks_404_and_unauthorized(self):
        user1 = make_user('13800000014')
        user2 = make_user('13800000015')
        other_note = make_note(user2, '他人笔记')
        client = auth_client(user1)

        # 不存在的 pk
        self.assertEqual(client.get('/api/notes/999999/backlinks/').status_code, 404)
        # 他人的 pk：同样 404，不泄露存在性
        self.assertEqual(client.get(f'/api/notes/{other_note.id}/backlinks/').status_code, 404)

        # 未登录：401
        anon = APIClient()
        self.assertEqual(anon.get(f'/api/notes/{other_note.id}/backlinks/').status_code, 401)

    # ---------- N+1 自证：查询数不随笔记条数增长 ----------
    def test_list_no_n_plus_one(self):
        user = make_user('13800000016')
        for i in range(5):
            make_note(user, f'笔记{i}', f'内容{i}')
        client = auth_client(user)

        # 计数查询 + 分页聚合查询 + tags 预取查询，共 3 条，与笔记数量无关
        with self.assertNumQueries(3):
            resp = client.get('/api/notes/?page_size=10')
        self.assertEqual(len(resp.data['results']), 5)

    def test_backlinks_no_n_plus_one(self):
        user = make_user('13800000017')
        target = make_note(user, '目标')
        client = auth_client(user)
        # 通过写接口创建引用方，链接才会解析
        for i in range(4):
            client.post('/api/notes/', {'title': f'来源{i}', 'content': '[[目标]]'}, format='json')

        # 目标存在性查询 1 条 + 引用方列表查询 1 条，与引用方数量无关
        with self.assertNumQueries(2):
            resp = client.get(f'/api/notes/{target.id}/backlinks/')
        self.assertEqual(len(resp.data), 4)
