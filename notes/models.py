from django.contrib.auth.base_user import BaseUserManager, AbstractBaseUser
from django.contrib.auth.models import PermissionsMixin
from django.db import models



class UserManager(BaseUserManager):
    """
       自定义用户管理器，负责创建用户和超级用户。
       继承BaseUserManager后，Django的createsuperuser命令和认证流程
       都会走这里定义的create_user/create_superuser方法。
    """
    def create_user(self, phone, password=None, **extra_fields):
        """
        创建普通用户。
        :param phone: 手机号，作为登录凭证（对应USERNAME_FIELD）
        :param password: 密码，会通过set_password()加密后存储
        :param extra_fields: 其他可选字段，如nickname、avatar等
        """
        if not phone:
            raise ValueError("手机号不能为空")
        # 创建用户实例 self.model 指向 User 类
        # 相当于 User(phone=phone, **extra_fields)
        user = self.model(phone=phone, **extra_fields)
        # 设置密码 set_password()会自动加密密码，存储为哈希值32位哈希值
        user.set_password(password)
        # 保存用户到数据库 ，using=self._db 表示使用当前数据库连接
        user.save(using=self._db)
        return user

    def create_superuser(self, phone, password=None, **extra_fields):
        """
        创建超级用户（管理员）。
        调用python manage.py createsuperuser时会走这个方法。
        is_staff=True 表示能登录Admin后台，is_superuser=True 表示拥有所有权限。
        """
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        return self.create_user(phone, password, **extra_fields)

class User(AbstractBaseUser, PermissionsMixin):
    """
    自定义用户模型，替代Django默认的auth.User。

    继承关系说明：
    - AbstractBaseUser：提供password、last_login、is_active等基础字段
      和认证所需的接口（get_username、check_password等）
    - PermissionsMixin：提供is_superuser、groups、user_permissions字段，
      支持Django的权限系统（虽然本项目暂时用不到，但Admin后台依赖它）
    """
    # 手机号 11位 唯一 作为登录账号
    phone = models.CharField('手机号', max_length=11, unique=True)

    # 昵称 可选 最长50字符 blank=True 表示表单允许为空
    nickname = models.CharField('昵称', max_length=50, blank=True)

    # 头像 存url地址 blank=True 表示表单允许为空
    avatar = models.URLField('头像', blank=True)

    # 账号是否可用 Flase时用户无法登录
    is_active = models.BooleanField('是否激活', default=True)

    # 是否能够登录Admin后台 普通用户Flase 超级用户True
    is_staff = models.BooleanField('是否管理员', default=False)

    # 注册时间 自动添加当前时间
    # auto_now_add=True 表示创建时自动添加当前时间，后续更新不会改变
    create_at = models.DateTimeField('注册时间', auto_now_add=True)

    # 指定使用上面定义的UserManager
    objects = UserManager()

    # 核心配置 告诉Django使用手机号作为登录凭证
    USERNAME_FIELD = 'phone'

    # 创建超级用户时，除了USERNAME_FIELD和password外，还要求必填哪些字段
    # 这里为空列表，表示只需要手机号和密码就能创建用户
    REQUIRED_FIELDS = []

    class Meta:
        # Admin后台显示的中文名称（单数）
        verbose_name = '用户'
        # Admin后台显示的中文名称（复数）
        verbose_name_plural = '用户'

    def __str__(self):
        """
        打印用户对象时显示手机号
        """
        return self.phone

    def has_perm(self, perm, obj=None):
        """
        判断用户是否有某个权限。
        本项目简化处理，直接返回True。
        如果要做细粒度权限控制，可以在这里写具体逻辑。
        ⚠ 必须实现，否则Admin后台会报AttributeError。
        """
        return True

    def has_module_perms(self, app_label):
        """
        判断用户是否有访问某个app的权限。
        同样简化返回True。
         必须实现，否则Admin后台会报AttributeError。
        """
        return True

class Category(models.Model):
    """
    笔记分类，比如"工作"、"学习"、"生活"。
    一个分类下可以有多条笔记（一对多关系）。
    """
    name = models.CharField('分类名称', max_length=50)
    owner = models.ForeignKey(
        'notes.User',
        on_delete=models.CASCADE,
        related_name='categories',
        verbose_name='所属用户',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
        verbose_name = '分类'
        verbose_name_plural = '分类'
        unique_together = ['owner', 'name']  # 同一用户下分类名不重复

    def __str__(self):
        return self.name


class Tag(models.Model):
    """
    笔记标签，比如"Python"、"面试"、"待办"。
    一个笔记可以有多个标签，一个标签也可以属于多个笔记（多对多关系）。
    """
    name = models.CharField('标签名称', max_length=30)
    owner = models.ForeignKey(
        'notes.User',
        on_delete=models.CASCADE,
        related_name='tags',
        verbose_name='所属用户',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = '标签'
        verbose_name_plural = '标签'
        unique_together = ['owner', 'name']  # 同一用户下标签名不重复

    def __str__(self):
        return self.name

class NoteDeleteManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)

class Note(models.Model):
    """
    笔记模型，每条笔记属于一个用户。
    on_delete=models.CASCADE 表示用户被删除时，他的笔记也一起删掉。
    """
    title = models.CharField('标题', max_length=50)
    content = models.TextField('内容')
    category = models.ForeignKey(
        'notes.Category',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='notes',
        verbose_name='分类',
    )
    tags = models.ManyToManyField(
        'notes.Tag',
        blank=True,
        related_name='notes',
        verbose_name='标签',
    )
    owner = models.ForeignKey(
        'notes.User',
        on_delete=models.CASCADE,
        related_name='notes',
        verbose_name='作者',
    )
    create_at = models.DateTimeField('创建时间', auto_now_add=True)
    update_at = models.DateTimeField('更新时间', auto_now=True)
    is_deleted = models.BooleanField(default=False, verbose_name='是否删除')
    is_pinned = models.BooleanField(default=False, verbose_name='是否置顶')

    class Meta:
        ordering = ['-is_pinned', '-create_at']  # 置顶优先，再按创建时间降序
        verbose_name = '笔记'
        verbose_name_plural = '笔记'

    objects = NoteDeleteManager()      # 默认查询，自动过滤已删除的
    all_objects = models.Manager()     # 查所有笔记（包括已删除），回收站用

    def __str__(self):
        return self.title
