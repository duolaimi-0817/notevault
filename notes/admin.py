from django.contrib import admin
from .models import User, Category, Note


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    """
    用户管理页面。
    list_display 控制列表页显示哪些字段。
    search_fields 让Admin顶部出现搜索框，可以按手机号搜索用户。
    """
    list_display = ['phone', 'nickname', 'is_active', 'is_staff', 'create_at']
    search_fields = ['phone', 'nickname']
    list_filter = ['is_active', 'is_staff']


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    """分类管理页面"""
    list_display = ['name', 'owner', 'created_at']
    search_fields = ['name']
    list_filter = ['owner']


@admin.register(Note)
class NoteAdmin(admin.ModelAdmin):
    """
    笔记管理页面。
    list_display 中 'owner__phone' 表示跨表查询，显示笔记作者的手机号。
    双下划线是Django ORM的跨关系查询语法。
    """
    list_display = ['title', 'owner__phone', 'category', 'create_at', 'update_at']
    search_fields = ['title', 'content']
    list_filter = ['category', 'owner']