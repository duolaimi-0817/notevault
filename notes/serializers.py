from rest_framework import serializers

from notes.models import User, Note, Category, Tag


class RegisterSerializer(serializers.ModelSerializer):
    """
    注册接口的序列化器。
    ModelSerializer会根据User模型自动生成字段验证，
    但密码需要特殊处理——不能明文存储，所以重写create方法。
    """
    # write_only=True 表示密码字段仅在序列化时使用，不会在反序列化时使用
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = ['phone', 'password', 'nickname']

    def create(self, validated_data):
        nickname = validated_data.pop('nickname', '')
        user = User.objects.create_user(
            phone=validated_data['phone'],
            password=validated_data['password'],
            nickname=nickname,
        )
        return user

class LoginSerializer(serializers.Serializer):
    """
    登录接口的序列化器。
    登录不需要创建数据库记录，所以用普通Serializer而非ModelSerializer。
    只负责验证前端传来的手机号和密码格式是否正确。
    """
    phone = serializers.CharField(max_length=11)
    password = serializers.CharField(write_only=True)


class TagSerializer(serializers.ModelSerializer):
    """标签序列化器"""
    class Meta:
        model = Tag
        fields = ['id', 'name', 'created_at']
        read_only_fields = ['created_at']
        extra_kwargs = {
            'name': {
                'error_messages': {
                    'blank': '标签名称不能为空',
                    'max_length': '标签名称不能超过30个字符',
                }
            }
        }

    def validate_name(self, value):
        """验证标签名称在同一用户下是否唯一"""
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            exclude_id = self.instance.id if self.instance else None
            queryset = Tag.objects.filter(owner=request.user, name=value)
            if exclude_id:
                queryset = queryset.exclude(id=exclude_id)
            if queryset.exists():
                raise serializers.ValidationError('该标签名称已存在')
        return value


class NoteSerializer(serializers.ModelSerializer):
    """
    笔记序列化器。
    read_only=True 的字段只能读不能写：
    - owner：自动设为当前登录用户，不允许前端指定
    - created_at / updated_at：自动生成，不允许前端修改
    """
    owner = serializers.ReadOnlyField(source='owner.phone')
    category_name = serializers.ReadOnlyField(source='category.name')
    tags = TagSerializer(many=True, read_only=True)
    tag_ids = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=Tag.objects.all(),
        required=False,
        write_only=True,
        source='tags'
    )
    # 双向链接统计：列表接口由 with_link_counts() 注解提供；
    # 未注解的单个对象场景退化为一次 count 查询（不存在 N+1）。
    link_count = serializers.SerializerMethodField()
    backlink_count = serializers.SerializerMethodField()
    # 本次保存后解析不出的 [[标题]]（仅保存接口通过 context 传入，其余场景给默认值）
    unresolved_link_count = serializers.SerializerMethodField()
    unresolved_link_titles = serializers.SerializerMethodField()

    class Meta:
        model = Note
        fields = ['id', 'title', 'content', 'category', 'category_name', 'tags', 'tag_ids',
                  'owner', 'is_pinned', 'create_at', 'update_at',
                  'link_count', 'backlink_count', 'unresolved_link_count', 'unresolved_link_titles']
        read_only_fields = ['owner', 'create_at', 'update_at', 'tags']

    def get_link_count(self, obj):
        annotated = getattr(obj, 'link_count', None)
        if annotated is not None:
            return annotated
        return obj.outgoing_links.count()

    def get_backlink_count(self, obj):
        annotated = getattr(obj, 'backlink_count', None)
        if annotated is not None:
            return annotated
        return obj.backlinks.filter(source__is_deleted=False).count()

    def get_unresolved_link_count(self, obj):
        return self.context.get('unresolved_link_count', 0)

    def get_unresolved_link_titles(self, obj):
        return self.context.get('unresolved_link_titles', [])

class CategorySerializer(serializers.ModelSerializer):
    """分类序列化器，note_count统计该分类下有多少条笔记"""
    note_count = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = ['id', 'name', 'note_count', 'created_at']
        read_only_fields = ['created_at']
        extra_kwargs = {
            'name': {
                'error_messages': {
                    'blank': '分类名称不能为空',
                    'max_length': '分类名称不能超过50个字符',
                }
            }
        }

    def get_note_count(self, obj):
        """SerializerMethodField需要手动写方法，返回分类下的笔记数量"""
        return obj.notes.count()

    def validate_name(self, value):
        """验证分类名称在同一用户下是否唯一"""
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            # 排除当前实例（更新时）
            exclude_id = self.instance.id if self.instance else None
            queryset = Category.objects.filter(owner=request.user, name=value)
            if exclude_id:
                queryset = queryset.exclude(id=exclude_id)
            if queryset.exists():
                raise serializers.ValidationError('该分类名称已存在')
        return value
