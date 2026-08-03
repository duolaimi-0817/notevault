from datetime import timedelta

from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate

from .models import Note, Category, Tag
from .serializers import RegisterSerializer, LoginSerializer, NoteSerializer, CategorySerializer, TagSerializer


class RegisterView(APIView):
    """
    用户注册接口。
    前端POST请求，body传 {phone, password, nickname}
    注册成功后自动返回JWT token，前端拿到token后就不用再调登录接口了。
    """
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        # data=request.data 把前端传来的JSON数据交给序列化器验证
        serializer.is_valid(raise_exception=True)
        # is_valid()验证数据格式，raise_exception=True表示验证失败直接返回400错误
        user = serializer.save()
        # 调用上面的create()方法，加密密码并保存到数据库

        # 手动生成JWT token
        refresh = RefreshToken.for_user(user)
        return Response({
            'user': {
                'phone': user.phone,
                'nickname': user.nickname,
            },
            'access': str(refresh.access_token),
            'refresh': str(refresh),
        }, status=status.HTTP_201_CREATED)


class LoginView(APIView):
    """
    用户登录接口。
    前端POST请求，body传 {phone, password}
    验证成功后返回JWT token。
    """
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # authenticate验证用户身份
        # ⚠ 注意：因为我们自定义了USERNAME_FIELD='phone'，
        # 但authenticate内部还是用username参数名，所以这里传username=phone的值
        user = authenticate(
            username=serializer.validated_data['phone'],
            password=serializer.validated_data['password'],
        )

        if user is None:
            return Response(
                {'error': '手机号或密码错误'},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        refresh = RefreshToken.for_user(user)
        return Response({
            'user': {
                'phone': user.phone,
                'nickname': user.nickname,
            },
            'access': str(refresh.access_token),
            'refresh': str(refresh),
        })


class LogoutView(APIView):
    """
    用户登出接口。
    JWT是无状态的，服务端没有session可删，
    所以"登出"实际上就是让前端删掉本地存的token。
    这个接口返回204表示成功，前端收到后清除token即可。
    """
    permission_classes = [IsAuthenticated]  # 必须登录才能调用

    def post(self, request):
        return Response(status=status.HTTP_204_NO_CONTENT)

class NoteListView(APIView):
    """
    笔记列表 + 创建笔记。
    GET：获取当前用户的所有笔记（支持分页和搜索）
         参数：q=搜索关键词, page=页码, page_size=每页数量(默认10)
    POST：创建一条新笔记
    """
    permission_classes = [IsAuthenticated]  # 必须登录才能调用
    def get(self, request):
        notes = Note.objects.filter(owner=request.user)
        # 搜索过滤
        keyword = request.query_params.get('q', '').strip()
        if keyword:
            notes = notes.filter(
                Q(title__icontains=keyword) | Q(content__icontains=keyword)
            )
        # 分类过滤
        category_id = request.query_params.get('category', '').strip()
        if category_id:
            notes = notes.filter(category_id=category_id)
        # 标签过滤
        tag_id = request.query_params.get('tag', '').strip()
        if tag_id:
            notes = notes.filter(tags__id=tag_id)

        # 分页
        from django.core.paginator import Paginator
        page_size = request.query_params.get('page_size', 10)
        try:
            page_size = int(page_size)
            if page_size <= 0:
                page_size = 10
            if page_size > 100:
                page_size = 100
        except (ValueError, TypeError):
            page_size = 10

        paginator = Paginator(notes, page_size)
        page_num = request.query_params.get('page', 1)
        try:
            page_num = int(page_num)
        except (ValueError, TypeError):
            page_num = 1

        page_obj = paginator.get_page(page_num)
        serializer = NoteSerializer(page_obj.object_list, many=True)

        return Response({
            'results': serializer.data,
            'total': paginator.count,
            'page': page_obj.number,
            'page_size': page_size,
            'total_pages': paginator.num_pages,
        })

    def post(self, request):
        serializer = NoteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(owner=request.user)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class NoteImportView(APIView):
    """
    导入 Markdown 文件为笔记。
    POST /api/notes/import/  上传 .md 文件（multipart/form-data）
    文件名（去掉 .md 后缀）作为笔记标题，文件内容作为笔记内容。
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        uploaded_file = request.FILES.get('file')
        if not uploaded_file:
            return Response({'error': '请上传一个文件'}, status=status.HTTP_400_BAD_REQUEST)

        # 检查文件扩展名
        if not uploaded_file.name.lower().endswith('.md'):
            return Response({'error': '只支持 .md 格式的 Markdown 文件'}, status=status.HTTP_400_BAD_REQUEST)

        # 读取文件内容（尝试 UTF-8 编码）
        try:
            content = uploaded_file.read().decode('utf-8')
        except UnicodeDecodeError:
            return Response({'error': '文件编码错误，请使用 UTF-8 编码'}, status=status.HTTP_400_BAD_REQUEST)

        # 用文件名（去掉 .md 后缀）作为标题
        title = uploaded_file.name
        if title.lower().endswith('.md'):
            title = title[:-3]
        # 标题过长则截断
        if len(title) > 50:
            title = title[:50]

        # 创建笔记
        note = Note.objects.create(
            title=title,
            content=content,
            owner=request.user,
        )
        serializer = NoteSerializer(note)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class NoteDetailView(APIView):
    """
    单条笔记的查看、修改、删除。
    通过URL中的id参数定位具体笔记。
    """
    permission_classes = [IsAuthenticated]

    def get_object(self, pk, user):
        """
        根据id查找笔记，同时验证是否属于当前用户。
        防止用户A通过改id访问用户B的笔记。
        """
        try:
            return Note.objects.get(id=pk, owner=user)
        except Note.DoesNotExist:
            return None

    def get(self, request, pk):
        note = self.get_object(pk, request.user)
        if note is None:
            return Response({'error': '笔记不存在'}, status=status.HTTP_404_NOT_FOUND)
        serializer = NoteSerializer(note)
        return Response(serializer.data)

    def put(self, request, pk):
        """
        修改笔记。put表示全量更新（所有字段都要传）。
        如果只需要改部分字段，应该用patch方法。
        """
        note = self.get_object(pk, request.user)
        if note is None:
            return Response({'error': '笔记不存在'}, status=status.HTTP_404_NOT_FOUND)
        serializer = NoteSerializer(note, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def delete(self, request, pk):
        note = self.get_object(pk, request.user)
        if note is None:
            return Response({'error': '笔记不存在'}, status=status.HTTP_404_NOT_FOUND)
        note.is_deleted = True
        note.save()
        return Response({'message': '笔记已移入回收站。'}, status=status.HTTP_200_OK)

class CategoryView(APIView):
    """
    分类的增删查。
    GET：获取当前用户的所有分类
    POST：创建新分类
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        categories = Category.objects.filter(owner=request.user)
        serializer = CategorySerializer(categories, many=True, context={'request': request})
        return Response(serializer.data)

    def post(self, request):
        serializer = CategorySerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        serializer.save(owner=request.user)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class CategoryDetailView(APIView):
    """
    单个分类的修改和删除。
    """
    permission_classes = [IsAuthenticated]

    def get_object(self, pk, user):
        try:
            return Category.objects.get(id=pk, owner=user)
        except Category.DoesNotExist:
            return None

    def put(self, request, pk):
        category = self.get_object(pk, request.user)
        if category is None:
            return Response({'error': '分类不存在'}, status=status.HTTP_404_NOT_FOUND)
        serializer = CategorySerializer(category, data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def delete(self, request, pk):
        category = self.get_object(pk, request.user)
        if category is None:
            return Response({'error': '分类不存在'}, status=status.HTTP_404_NOT_FOUND)
        category.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

class RecycleBinView(APIView):
    """
    回收站：查看已删除的笔记、恢复笔记、彻底删除笔记。
    GET：列出所有已删除的笔记
    POST：根据action参数执行不同操作
          action=restore → 恢复笔记
          action=delete → 彻底删除（不可恢复）
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # GET只需要列出已删除的笔记，不需要note_id
        notes = Note.all_objects.filter(owner=request.user, is_deleted=True)
        serializer = NoteSerializer(notes, many=True)
        return Response(serializer.data)

    def post(self, request):
        # POST才需要action和note_id
        action = request.data.get('action')
        note_id = request.data.get('note_id')

        if not note_id:
            return Response({'error': '缺少note_id'}, status=status.HTTP_400_BAD_REQUEST)

        note = Note.all_objects.filter(id=note_id, owner=request.user, is_deleted=True).first()
        if note is None:
            return Response({'error': '笔记不存在或不属于你'}, status=status.HTTP_404_NOT_FOUND)

        if action == 'restore':
            note.is_deleted = False
            note.save()
            return Response({'message': '笔记已恢复'})

        elif action == 'delete':
            note.delete()
            return Response({'message': '笔记已彻底删除'}, status=status.HTTP_204_NO_CONTENT)

        else:
            return Response({'error': '无效的action，可选restore或delete'}, status=status.HTTP_400_BAD_REQUEST)
class StatsView(APIView):
    """
    笔记统计接口，返回用户的笔记概览数据。
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        # 1. 笔记总数
        total_notes = Note.objects.filter(owner=user).count()

        # 2. 分类统计：每个分类下有多少条笔记
        category_stats = Note.objects.filter(
            owner=user, category__isnull=False
        ).values('category__name').annotate(
            count=Count('id')
        ).order_by('-count')

        # 3. 最近7天每天的笔记创建数量
        today = timezone.now().date()
        seven_days_ago = today - timedelta(days=6)
        daily_stats = Note.objects.filter(
            owner=user,
            create_at__date__gte=seven_days_ago,
            create_at__date__lte=today,
        ).values('create_at__date').annotate(
            count=Count('id')
        ).order_by('create_at__date')

        # 4. 回收站里的笔记数量
        trash_count = Note.all_objects.filter(owner=user, is_deleted=True).count()

        return Response({
            'total_notes': total_notes,
            'category_stats': list(category_stats),
            'daily_stats': [
                {'date': str(item['create_at__date']), 'count': item['count']}
                for item in daily_stats
            ],
            'trash_count': trash_count,
        })


class TagView(APIView):
    """
    标签的增删查。
    GET：获取当前用户的所有标签
    POST：创建新标签
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        tags = Tag.objects.filter(owner=request.user)
        serializer = TagSerializer(tags, many=True, context={'request': request})
        return Response(serializer.data)

    def post(self, request):
        serializer = TagSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        serializer.save(owner=request.user)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class TagDetailView(APIView):
    """
    单个标签的修改和删除。
    """
    permission_classes = [IsAuthenticated]

    def get_object(self, pk, user):
        try:
            return Tag.objects.get(id=pk, owner=user)
        except Tag.DoesNotExist:
            return None

    def put(self, request, pk):
        tag = self.get_object(pk, request.user)
        if tag is None:
            return Response({'error': '标签不存在'}, status=status.HTTP_404_NOT_FOUND)
        serializer = TagSerializer(tag, data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def delete(self, request, pk):
        tag = self.get_object(pk, request.user)
        if tag is None:
            return Response({'error': '标签不存在'}, status=status.HTTP_404_NOT_FOUND)
        tag.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


import markdown as md_lib
from django.http import HttpResponse
from xhtml2pdf import pisa
import io


class NoteExportView(APIView):
    """
    导出笔记为 Markdown 或 PDF 文件。
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        try:
            note = Note.objects.get(id=pk, owner=request.user)
        except Note.DoesNotExist:
            return Response({'error': '笔记不存在'}, status=status.HTTP_404_NOT_FOUND)

        # 用 'type' 而不是 'format'，避免和 DRF 内部的 format 参数冲突
        export_type = request.query_params.get('type', 'md').lower()
        filename = note.title or 'untitled'

        if export_type == 'md':
            response = HttpResponse(note.content, content_type='text/markdown; charset=utf-8')
            response['Content-Disposition'] = f'attachment; filename="{filename}.md"'
            return response

        elif export_type == 'pdf':
            html_body = md_lib.markdown(note.content, extensions=['extra', 'codehilite', 'toc'])
            html_doc = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<style>
    @page {{ size: A4; margin: 2cm; }}
    body {{ font-family: STSongStd-Light; font-size: 12px; line-height: 1.6; }}
    h1 {{ font-size: 22px; border-bottom: 1px solid #ccc; padding-bottom: 6px; }}
    h2 {{ font-size: 18px; }}
    h3 {{ font-size: 15px; }}
    code {{ background: #f4f4f4; padding: 2px 4px; font-size: 11px; }}
    pre {{ background: #f4f4f4; padding: 10px; overflow: wrap; font-size: 11px; }}
    blockquote {{ border-left: 3px solid #ccc; margin-left: 0; padding-left: 10px; color: #555; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border: 1px solid #ccc; padding: 6px 8px; text-align: left; }}
</style>
</head>
<body>
{html_body}
</body>
</html>"""
            buffer = io.BytesIO()
            pisa_status = pisa.CreatePDF(io.StringIO(html_doc), dest=buffer, encoding='utf-8')
            if pisa_status.err:
                return Response({'error': 'PDF 生成失败'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            buffer.seek(0)
            response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="{filename}.pdf"'
            return response

        else:
            return Response({'error': '不支持的导出格式，可选 md 或 pdf'}, status=status.HTTP_400_BAD_REQUEST)


class ChangePasswordView(APIView):
    """
    修改密码接口。
    POST /api/change-password/  body: { old_password, new_password }
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        old_password = request.data.get('old_password', '')
        new_password = request.data.get('new_password', '')

        if not old_password or not new_password:
            return Response({'error': '旧密码和新密码都不能为空'}, status=status.HTTP_400_BAD_REQUEST)

        # 验证旧密码
        if not request.user.check_password(old_password):
            return Response({'error': '旧密码错误'}, status=status.HTTP_400_BAD_REQUEST)

        # 验证新密码长度
        if len(new_password) < 8:
            return Response({'error': '新密码长度不能少于8位'}, status=status.HTTP_400_BAD_REQUEST)

        # 设置新密码
        request.user.set_password(new_password)
        request.user.save()
        return Response({'message': '密码修改成功'})


class NotePinView(APIView):
    """
    笔记置顶/取消置顶接口。
    POST /api/notes/<id>/pin/  body: { is_pinned: true/false }
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        try:
            note = Note.objects.get(id=pk, owner=request.user)
        except Note.DoesNotExist:
            return Response({'error': '笔记不存在'}, status=status.HTTP_404_NOT_FOUND)

        is_pinned = request.data.get('is_pinned', True)
        note.is_pinned = bool(is_pinned)
        note.save()
        return Response({'message': '已置顶' if note.is_pinned else '已取消置顶', 'is_pinned': note.is_pinned})


class BatchOperationView(APIView):
    """
    批量操作接口。
    POST /api/notes/batch/  body: { action: 'delete'|'pin'|'unpin', note_ids: [1,2,3] }
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        action = request.data.get('action', '')
        note_ids = request.data.get('note_ids', [])

        if not action:
            return Response({'error': '请指定操作类型'}, status=status.HTTP_400_BAD_REQUEST)
        if not note_ids or not isinstance(note_ids, list):
            return Response({'error': '请指定笔记ID列表'}, status=status.HTTP_400_BAD_REQUEST)

        # 只操作属于当前用户的笔记
        notes = Note.objects.filter(id__in=note_ids, owner=request.user)
        if not notes.exists():
            return Response({'error': '未找到指定笔记'}, status=status.HTTP_404_NOT_FOUND)

        if action == 'delete':
            notes.update(is_deleted=True)
            return Response({'message': f'已将 {notes.count()} 条笔记移至回收站'})
        elif action == 'pin':
            notes.update(is_pinned=True)
            return Response({'message': f'已置顶 {notes.count()} 条笔记'})
        elif action == 'unpin':
            notes.update(is_pinned=False)
            return Response({'message': f'已取消 {notes.count()} 条笔记的置顶'})
        else:
            return Response({'error': '不支持的操作类型，可选 delete/pin/unpin'}, status=status.HTTP_400_BAD_REQUEST)