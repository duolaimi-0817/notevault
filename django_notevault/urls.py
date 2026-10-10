from django.contrib import admin
from django.urls import path
from notes.views import RegisterView, LoginView, LogoutView, CategoryView, CategoryDetailView, NoteDetailView, \
    NoteListView, NoteImportView, RecycleBinView, StatsView, TagView, TagDetailView, NoteExportView, \
    ChangePasswordView, NotePinView, BatchOperationView, NoteBacklinksView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/register/', RegisterView.as_view()),
    path('api/login/', LoginView.as_view()),
    path('api/logout/', LogoutView.as_view()),
    path('api/change-password/', ChangePasswordView.as_view()),
    path('api/notes/', NoteListView.as_view()),
    path('api/notes/import/', NoteImportView.as_view()),
    path('api/notes/batch/', BatchOperationView.as_view()),
    path('api/notes/<int:pk>/pin/', NotePinView.as_view()),
    path('api/notes/<int:pk>/backlinks/', NoteBacklinksView.as_view()),
    path('api/export-note/<int:pk>/', NoteExportView.as_view()),
    path('api/notes/<int:pk>/', NoteDetailView.as_view()),
    path('api/categories/', CategoryView.as_view()),
    path('api/categories/<int:pk>/', CategoryDetailView.as_view()),
    path('api/tags/', TagView.as_view()),
    path('api/tags/<int:pk>/', TagDetailView.as_view()),
    path('api/recycle-bin/', RecycleBinView.as_view()),
    path('api/stats/', StatsView.as_view()),
]