from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from notes.models import Note, NoteLink, User


def make_user(phone='13800000001'):
    return User.objects.create_user(phone=phone, password='testpass123')


def make_note(owner, title, content='', **kwargs):
    return Note.objects.create(owner=owner, title=title, content=content, **kwargs)


class WikiLinkParsingTests(TestCase):
    """解析规则的纯函数级测试（代码块过滤、去重、自链接等）。"""

    def test_inline_and_fenced_code_are_ignored(self):
        from notes.links import extract_link_titles
        content = (
            '[[真实标题]]\n'
            '行内代码 `[[假标题1]]` 结束\n'
            '```python\n'
            '[[假标题2]]\n'
            '```\n'
            '~~~\n'
            '[[假标题3]]\n'
            '~~~\n'
            '双反引号 ``x [[假标题4]] y`` 收尾\n'
            '[[另一个真实标题]]\n'
        )
        self.assertEqual(extract_link_titles(content), ['真实标题', '另一个真实标题'])

    def test_duplicate_titles_kept_in_extraction_order(self):
        from notes.links import extract_link_titles
        self.assertEqual(
            extract_link_titles('[[A]] xx [[A]] [[B]]'),
            ['A', 'A', 'B'],
        )


class NoteLinkAPITests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.other = make_user('13800000002')
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.other_client = APIClient()
        self.other_client.force_authenticate(self.other)

    def create_via_api(self, client, title, content):
        return client.post('/api/notes/', {'title': title, 'content': content}, format='json')

    def get_note(self, client, note_id):
        return client.get(f'/api/notes/{note_id}/')

    def list_results(self, client):
        return client.get('/api/notes/', {'page_size': 100}).data['results']

    def result_by_id(self, client, note_id):
        return next(n for n in self.list_results(client) if n['id'] == note_id)

    # 1. 正常建链：同目标多次出现只建一条
    def test_normal_links_and_dedup(self):
        t1 = make_note(self.user, '目标一')
        t2 = make_note(self.user, '目标二')
        resp = self.create_via_api(self.client, '来源', '[[目标一]] 和 [[目标二]]，再说一次 [[目标一]]')
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data['link_count'], 2)
        self.assertEqual(resp.data['unresolved_link_count'], 0)
        self.assertEqual(resp.data['unresolved_link_titles'], [])
        self.assertEqual(
            set(NoteLink.objects.values_list('source_id', 'target_id')),
            {(resp.data['id'], t1.id), (resp.data['id'], t2.id)},
        )
        # 被引用方的反向引用计数
        self.assertEqual(self.result_by_id(self.client, t1.id)['backlink_count'], 1)
        self.assertEqual(self.result_by_id(self.client, t2.id)['backlink_count'], 1)

    # 2. 同名标题取 create_at 最早者
    def test_duplicate_title_resolves_earliest(self):
        older = make_note(self.user, '同名')
        newer = make_note(self.user, '同名')
        resp = self.create_via_api(self.client, '引用方', '[[同名]]')
        link = NoteLink.objects.get(source_id=resp.data['id'])
        self.assertEqual(link.target_id, older.id)
        self.assertNotEqual(link.target_id, newer.id)

    # 3. 跨用户隔离：任何时候都不能链接到别人的笔记
    def test_cross_user_isolation(self):
        make_note(self.user, '我的私有标题')
        resp = self.create_via_api(self.other_client, '外人的笔记', '[[我的私有标题]]')
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data['link_count'], 0)
        self.assertEqual(resp.data['unresolved_link_count'], 1)
        self.assertEqual(resp.data['unresolved_link_titles'], ['我的私有标题'])
        self.assertFalse(NoteLink.objects.exists())

    # 4. 指向自己的链接忽略
    def test_self_link_ignored(self):
        resp = self.create_via_api(self.client, '就是我', '前文 [[就是我]] 后文')
        self.assertEqual(resp.data['link_count'], 0)
        self.assertEqual(resp.data['unresolved_link_count'], 0)
        self.assertFalse(NoteLink.objects.exists())

    # 5. 代码块内的链接不算（接口端到端）
    def test_code_block_links_not_created(self):
        make_note(self.user, '真实')
        resp = self.create_via_api(
            self.client, '代码演示',
            '[[真实]]\n`[[假1]]`\n```\n[[假2]]\n```\n',
        )
        self.assertEqual(resp.data['link_count'], 1)
        self.assertEqual(NoteLink.objects.count(), 1)
        self.assertEqual(NoteLink.objects.get().target.title, '真实')
        self.assertEqual(resp.data['unresolved_link_count'], 0)

    # 6. 目标在回收站：关系保留；已删目标仍可被解析为目标（标记失效）
    def test_link_kept_when_target_soft_deleted(self):
        from notes.links import with_link_counts
        target = make_note(self.user, '会被删的目标')
        source_id = self.create_via_api(self.client, '引用者', '[[会被删的目标]]').data['id']
        self.assertEqual(NoteLink.objects.count(), 1)

        # 软删目标（经单条删除接口）
        resp = self.client.delete(f'/api/notes/{target.id}/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(NoteLink.objects.count(), 1, '软删目标后关系必须保留')

        # 对一个已经在回收站的目标，新保存的正文仍建立关系（失效但保留）
        resp2 = self.create_via_api(self.client, '后来的引用者', '[[会被删的目标]]')
        self.assertEqual(resp2.data['link_count'], 1)
        self.assertEqual(NoteLink.objects.count(), 2)
        self.assertEqual(NoteLink.objects.filter(source_id=source_id).count(), 1)

        # 关系保留但失效可派生：目标虽在回收站，其 backlink_count 只看引用方是否未删 -> 2
        deleted_target = with_link_counts(Note.all_objects.filter(id=target.id)).first()
        self.assertEqual(deleted_target.backlink_count, 2)
        self.assertEqual(deleted_target.link_count, 0)

    # 7. 批量删除（queryset.update 路径）后 backlink_count 正确，关系行仍保留
    def test_backlink_count_after_batch_delete(self):
        target = make_note(self.user, '被引用的笔记')
        referrer_id = self.create_via_api(self.client, '引用方', '[[被引用的笔记]]').data['id']
        self.assertEqual(self.result_by_id(self.client, target.id)['backlink_count'], 1)

        resp = self.client.post('/api/notes/batch/', {
            'action': 'delete', 'note_ids': [referrer_id],
        }, format='json')
        self.assertEqual(resp.status_code, 200)

        # 计数只算未软删引用方 -> 0；但关系行保留
        self.assertEqual(self.result_by_id(self.client, target.id)['backlink_count'], 0)
        self.assertTrue(NoteLink.objects.filter(source_id=referrer_id, target_id=target.id).exists())

        # backlinks 接口仍列出已软删的引用方，带 is_deleted=true
        bl = self.client.get(f'/api/notes/{target.id}/backlinks/')
        self.assertEqual(bl.status_code, 200)
        self.assertEqual(len(bl.data), 1)
        self.assertEqual(bl.data[0]['id'], referrer_id)
        self.assertTrue(bl.data[0]['is_deleted'])

    # 8. restore 后关系重新生效
    def test_restore_reactivates_links(self):
        target = make_note(self.user, '恢复目标')
        referrer_id = self.create_via_api(self.client, '被恢复的引用方', '[[恢复目标]]').data['id']
        self.client.post('/api/notes/batch/', {'action': 'delete', 'note_ids': [referrer_id]}, format='json')
        self.assertEqual(self.result_by_id(self.client, target.id)['backlink_count'], 0)

        resp = self.client.post('/api/recycle-bin/', {
            'action': 'restore', 'note_id': referrer_id,
        }, format='json')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self.result_by_id(self.client, target.id)['backlink_count'], 1)

    # 9. 彻底删除目标 -> CASCADE 清除关系
    def test_hard_delete_cascades_links(self):
        target = make_note(self.user, '彻底删除目标')
        self.create_via_api(self.client, '引用者甲', '[[彻底删除目标]]')
        self.create_via_api(self.client, '引用者乙', '[[彻底删除目标]]')
        self.assertEqual(NoteLink.objects.count(), 2)

        # 回收站彻底删除（先软删再硬删）
        self.client.delete(f'/api/notes/{target.id}/')
        resp = self.client.post('/api/recycle-bin/', {
            'action': 'delete', 'note_id': target.id,
        }, format='json')
        self.assertEqual(resp.status_code, 204)
        self.assertFalse(NoteLink.objects.exists())

    # 10. backlinks 接口：404 与越权
    def test_backlinks_404_and_permission(self):
        target = make_note(self.user, '我的笔记')

        # 不存在的 pk -> 404
        resp = self.client.get('/api/notes/999999/backlinks/')
        self.assertEqual(resp.status_code, 404)

        # 别人的笔记 pk -> 404，不能泄露存在性
        resp = self.other_client.get(f'/api/notes/{target.id}/backlinks/')
        self.assertEqual(resp.status_code, 404)

        # 未登录 -> 401
        anon = APIClient()
        resp = anon.get(f'/api/notes/{target.id}/backlinks/')
        self.assertEqual(resp.status_code, 401)

    # 11. backlinks 返回字段、排序，且包含软删引用方
    def test_backlinks_fields_order_and_deleted(self):
        target = make_note(self.user, '汇总目标')
        # 创建顺序刻意安排：deleted 最早，plain 次之（未置顶里更新），pinned 最晚且置顶
        deleted_id = self.create_via_api(self.client, '已删引用', '[[汇总目标]]').data['id']
        plain_id = self.create_via_api(self.client, '普通引用', '[[汇总目标]]').data['id']
        pinned_id = self.create_via_api(self.client, '置顶引用', '[[汇总目标]]').data['id']
        Note.all_objects.filter(id=deleted_id).update(is_deleted=True)
        Note.all_objects.filter(id=pinned_id).update(is_pinned=True)

        resp = self.client.get(f'/api/notes/{target.id}/backlinks/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual([item['id'] for item in resp.data], [pinned_id, plain_id, deleted_id])
        self.assertEqual(
            set(resp.data[0].keys()),
            {'id', 'title', 'create_at', 'is_pinned', 'is_deleted'},
        )
        flags = {item['id']: item['is_deleted'] for item in resp.data}
        self.assertEqual(flags, {pinned_id: False, plain_id: False, deleted_id: True})

    # 12. PUT 修改正文后链接重建（删除旧链接、未解析随响应返回）
    def test_put_rebuilds_links(self):
        make_note(self.user, '旧目标')
        make_note(self.user, '新目标')
        source_id = self.create_via_api(self.client, '来源', '[[旧目标]]').data['id']
        self.assertEqual(NoteLink.objects.count(), 1)

        resp = self.client.put(
            f'/api/notes/{source_id}/',
            {'title': '来源', 'content': '[[新目标]] 与 [[不存在的标题]]'},
            format='json',
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['link_count'], 1)
        self.assertEqual(resp.data['unresolved_link_count'], 1)
        self.assertEqual(resp.data['unresolved_link_titles'], ['不存在的标题'])
        self.assertEqual(NoteLink.objects.get().target.title, '新目标')

    # 13. 导入入口同样建链
    def test_import_creates_links(self):
        make_note(self.user, '导入目标')
        upload = SimpleUploadedFile('来源文件.md', '正文 [[导入目标]]'.encode('utf-8'))
        resp = self.client.post('/api/notes/import/', {'file': upload}, format='multipart')
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data['title'], '来源文件')
        self.assertEqual(resp.data['link_count'], 1)
        self.assertEqual(NoteLink.objects.count(), 1)

    # 14. 批量置顶不动链接
    def test_batch_pin_keeps_links(self):
        make_note(self.user, '目标')
        source_id = self.create_via_api(self.client, '来源', '[[目标]]').data['id']
        self.client.post('/api/notes/batch/', {'action': 'pin', 'note_ids': [source_id]}, format='json')
        self.assertEqual(NoteLink.objects.count(), 1)
        self.client.post('/api/notes/batch/', {'action': 'unpin', 'note_ids': [source_id]}, format='json')
        self.assertEqual(NoteLink.objects.count(), 1)

    # 15. N+1 自证：笔记数翻倍，列表查询数不变
    def test_note_list_has_no_n_plus_one(self):
        def seed(count):
            for i in range(count):
                make_note(self.user, f'笔记{i}', f'[[被引用的公共目标 {i}]]')

        make_note(self.user, '被引用的公共目标 0')
        seed(3)
        with CaptureQueriesContext(connection) as ctx_small:
            resp = self.client.get('/api/notes/', {'page_size': 100})
        self.assertEqual(resp.status_code, 200)
        small_queries = len(ctx_small.captured_queries)

        seed(3)
        with CaptureQueriesContext(connection) as ctx_large:
            resp = self.client.get('/api/notes/', {'page_size': 100})
        self.assertEqual(resp.status_code, 200)
        large_queries = len(ctx_large.captured_queries)

        self.assertEqual(small_queries, large_queries, '笔记数量增加后查询数不应变化（存在 N+1）')
        # 固定为：COUNT 1 + 列表（含两个统计子查询、category join）1 + tags prefetch 1
        self.assertEqual(small_queries, 3)

    # 16. backlinks 接口本身恒定 2 条 SQL（目标定位 + 引用方列表）
    def test_backlinks_query_count(self):
        target = make_note(self.user, '目标')
        for i in range(5):
            self.create_via_api(self.client, f'引用{i}', '[[目标]]')
        with self.assertNumQueries(2):
            resp = self.client.get(f'/api/notes/{target.id}/backlinks/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data), 5)
