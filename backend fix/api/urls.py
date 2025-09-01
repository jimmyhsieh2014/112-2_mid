# backend/api/urls.py

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework.authtoken.views import obtain_auth_token

from .views import (
    RegisterAPIView,
    LogoutView,
    MoodLogViewSet,
    DiaryViewSet,
    PhotoViewSet,
    TodoViewSet,
    # ⬇️ 新增：成就 / 領取 / 錢包
    AchievementListView,
    AchievementClaimView,
    WalletView,
    # 若要用客製化登入，改用下面這個
    # CustomObtainAuthToken,
)

router = DefaultRouter()
router.register(r'moodlogs', MoodLogViewSet, basename='moodlog')
router.register(r'diaries', DiaryViewSet, basename='diary')
router.register(r'photos', PhotoViewSet, basename='photo')
router.register(r'todos', TodoViewSet, basename='todo')

urlpatterns = [
    # 1. 使用者註冊 / 登入 / 登出
    path('auth/register/', RegisterAPIView.as_view(), name='register'),
    path('auth/login/', obtain_auth_token, name='login'),
    # path('auth/login/', CustomObtainAuthToken.as_view(), name='login'),
    path('auth/logout/', LogoutView.as_view(), name='logout'),

    # 2. ViewSets
    path('', include(router.urls)),

    # 3. 成就 & 錢包
    # 成就列表（含可領/已領狀態）
    path('achievements/', AchievementListView.as_view(), name='achievements'),
    # 手動領取情緒餘額
    path('achievements/claim/', AchievementClaimView.as_view(), name='achievements-claim'),
    # 錢包（查餘額與最近流水）
    path('wallet/', WalletView.as_view(), name='wallet'),
]
