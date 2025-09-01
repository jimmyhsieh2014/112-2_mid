# backend/api/views.py
from django.contrib.auth.models import User
from django.db import IntegrityError
from django.db.models import F
from django.utils import timezone
from django.utils.dateparse import parse_date
from datetime import datetime, timedelta

from rest_framework import (
    generics, viewsets, permissions, status, parsers, authentication
)
    # serializers as drf_serializers 只在舊的 AchievementListView 內嵌用到，現在可移除
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.authtoken.models import Token
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.views import APIView
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated

from .models import (
    MoodLog, Diary, Photo, UserAchievementProgress, Todo,
    Achievement, ExpLog
)
from .serializers import (
    UserRegisterSerializer,
    MoodLogSerializer,
    DiarySerializer,
    PhotoSerializer,
    UserAchievementSerializer,  # 保留
    TodoSerializer,
)
from .utils.emotion_models import analyze_sentiment

# ✅ 成就/錢包共用邏輯改用 utils，避免重複
from .utils.achievement import (
    update_achievement_progress,
    claim_achievement,
    get_status,
    current_balance,
    is_claimable,
)


# ===================== 使用者註冊 / 登入 / 登出 =====================

class RegisterAPIView(generics.CreateAPIView):
    serializer_class = UserRegisterSerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            user = serializer.save()
            token, _ = Token.objects.get_or_create(user=user)
            return Response(
                {'username': user.username, 'email': user.email, 'token': token.key},
                status=status.HTTP_201_CREATED
            )
        except IntegrityError:
            raise ValidationError({"error": "帳號或 Email 已存在，請更換後再試。"})


class CustomObtainAuthToken(ObtainAuthToken):
    """回傳 token 與 username（若想用此登入，請在 urls.py 切換路由）"""
    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        token = Token.objects.get(key=response.data['token'])
        user = token.user
        return Response({'token': token.key, 'username': user.username})


class LogoutView(generics.GenericAPIView):
    authentication_classes = [authentication.TokenAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        Token.objects.filter(user=request.user).delete()
        return Response({'detail': '已成功登出。'}, status=status.HTTP_200_OK)


# ===================== 心情紀錄 =====================

class MoodLogViewSet(viewsets.ModelViewSet):
    serializer_class = MoodLogSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return MoodLog.objects.filter(user=self.request.user).order_by('id')

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


# ===================== 日記（含 AI、月概覽、依日期取全文） =====================

class DiaryViewSet(viewsets.ModelViewSet):
    """
    標準端點：
      - GET    /api/diaries/
      - POST   /api/diaries/               建立日記（這裡做 upsert：同一天存在就更新）
      - PATCH  /api/diaries/{id}/          編輯日記（內容改變會重新分析）

    自訂端點：
      - GET    /api/diaries/overview/?month=YYYY-MM
      - GET    /api/diaries/by-date/YYYY-MM-DD/
    """
    serializer_class = DiarySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Diary.objects.filter(user=self.request.user).order_by('-created_at')

    @staticmethod
    def _has_field(obj, field_name: str) -> bool:
        return hasattr(obj, field_name)

    def _set_if_exists(self, obj, field_name: str, value):
        if self._has_field(obj, field_name):
            setattr(obj, field_name, value)

    # ---------- 新增（含 AI 分析；同一天 upsert） ----------
    def create(self, request, *args, **kwargs):
        user = request.user
        content = (request.data.get("content") or "").strip()
        emotion = request.data.get("emotion", "") or ""  # 舊欄位相容
        title = request.data.get("title")
        mood = request.data.get("mood")
        mood_color = request.data.get("mood_color")
        weather_icon = request.data.get("weather_icon")

        if not content:
            return Response({"error": "日記內容不得為空"}, status=status.HTTP_400_BAD_REQUEST)

        # 解析日期：未傳就用今天（建議前端也一併傳）
        date_str = request.data.get("date")
        if date_str:
            dt = parse_date(date_str)
            if not dt:
                return Response({"detail": "date 格式錯誤，需 YYYY-MM-DD"}, status=400)
        else:
            dt = timezone.localdate()

        # 分析情緒
        label, ai_message, keywords, topics = analyze_sentiment(content)

        # 🔁 upsert：同一天已存在 → 視為更新，避免 UNIQUE(user,date) 衝突
        diary = Diary.objects.filter(user=user, date=dt).first()
        if diary:
            diary.content = content
            if hasattr(diary, 'emotion'):
                diary.emotion = emotion
            if hasattr(diary, 'title') and title is not None:
                diary.title = title
            if hasattr(diary, 'mood') and mood:
                diary.mood = mood
            if hasattr(diary, 'mood_color') and mood_color:
                diary.mood_color = mood_color
            if hasattr(diary, 'weather_icon') and weather_icon:
                diary.weather_icon = weather_icon

            if hasattr(diary, 'sentiment'):
                diary.sentiment = label
            if hasattr(diary, 'ai_message'):
                diary.ai_message = ai_message
            if hasattr(diary, 'keywords'):
                diary.keywords = ", ".join(keywords)
            if hasattr(diary, 'topics'):
                diary.topics = ", ".join(topics)
            diary.save()

            return Response({
                "success": True,
                "id": diary.id,
                "label": label,
                "ai_message": ai_message,
                "updated": True,
            }, status=200)

        # 🆕 沒有則新增
        diary = Diary(user=user, content=content, date=dt)
        if hasattr(diary, 'emotion'):
            diary.emotion = emotion
        if hasattr(diary, 'title') and title is not None:
            diary.title = title
        if hasattr(diary, 'mood') and mood:
            diary.mood = mood
        if hasattr(diary, 'mood_color') and mood_color:
            diary.mood_color = mood_color
        if hasattr(diary, 'weather_icon') and weather_icon:
            diary.weather_icon = weather_icon
        if hasattr(diary, 'sentiment'):
            diary.sentiment = label
        if hasattr(diary, 'ai_message'):
            diary.ai_message = ai_message
        if hasattr(diary, 'keywords'):
            diary.keywords = ", ".join(keywords)
        if hasattr(diary, 'topics'):
            diary.topics = ", ".join(topics)
        diary.save()

        # 成就：只記錄進度，不自動發點數（手動領取）
        try:
            update_achievement_progress(user, 'first_diary', increment=1.0)
            update_achievement_progress(user, 'third_diary', increment=1.0)
        except Exception:
            pass

        return Response({
            "success": True,
            "id": diary.id,
            "label": label,
            "ai_message": ai_message,
            "updated": False,
        }, status=201)

    # ---------- 編輯（PATCH；內容改變則重新分析） ----------
    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        dirty = False  # 是否需要重新分析

        content = request.data.get('content')
        title = request.data.get('title')
        date_str = request.data.get('date')
        mood = request.data.get('mood')
        mood_color = request.data.get('mood_color')
        weather_icon = request.data.get('weather_icon')

        if content is not None and content != getattr(instance, 'content', None):
            instance.content = content
            dirty = True

        if title is not None and self._has_field(instance, 'title'):
            instance.title = title

        if date_str and self._has_field(instance, 'date'):
            dt = parse_date(date_str)
            if not dt:
                return Response({"detail": "date 格式錯誤，需 YYYY-MM-DD"}, status=400)
            instance.date = dt

        if mood and self._has_field(instance, 'mood'):
            instance.mood = mood
        if mood_color and self._has_field(instance, 'mood_color'):
            instance.mood_color = mood_color
        if weather_icon and self._has_field(instance, 'weather_icon'):
            instance.weather_icon = weather_icon

        if dirty:
            try:
                label, ai_message, keywords, topics = analyze_sentiment(instance.content or "")
                self._set_if_exists(instance, 'sentiment', label)
                self._set_if_exists(instance, 'ai_message', ai_message)
                self._set_if_exists(instance, 'keywords', ", ".join(keywords))
                self._set_if_exists(instance, 'topics', ", ".join(topics))
            except Exception:
                pass

        instance.save()
        return Response({"success": True, "data": DiarySerializer(instance).data}, status=200)

     # ---------- 月概覽：/api/diaries/overview/?month=YYYY-MM ----------
    @action(detail=False, methods=['get'], url_path='overview')
    def overview(self, request):
        month = request.query_params.get('month')
        if not month or len(month) != 7 or month[4] != '-':
            return Response({'detail': '請使用 month=YYYY-MM'}, status=400)
        try:
            year = int(month[:4])
            mon = int(month[-2:])
        except ValueError:
            return Response({'detail': 'month 格式錯誤，需 YYYY-MM'}, status=400)

        qs = self.get_queryset()
        if self._has_field(Diary(), 'date'):
            qs = qs.filter(date__year=year, date__month=mon).order_by('date')
        else:
            qs = qs.filter(created_at__year=year, created_at__month=mon).order_by('created_at')

        result = []
        for obj in qs:
            d = obj.date if self._has_field(obj, 'date') and obj.date else (obj.created_at or timezone.now()).date()

            # ✅ 新增：AI 預覽欄位
            ai_msg = (getattr(obj, 'ai_message', '') or '').strip()
            ai_prev = ai_msg.replace('\n', ' ')[:50] if ai_msg else ''

            result.append({
                'id': obj.id,
                'date': d.isoformat(),
                'mood': getattr(obj, 'mood', None) or getattr(obj, 'emotion', None),
                'icon': getattr(obj, 'weather_icon', None),
                'color': getattr(obj, 'mood_color', None),
                'has_diary': True,
                'snippet': (obj.content or '')[:60],
                # ✅ 新增這兩個鍵
                'has_ai': bool(ai_msg),
                'ai_preview': ai_prev,
            })
        return Response(result, status=200)

    # ---------- 依日期取全文：/api/diaries/by-date/YYYY-MM-DD/ ----------
    @action(detail=False, methods=['get'], url_path=r'by-date/(?P<date_str>\d{4}-\d{2}-\d{2})')
    def by_date(self, request, date_str=None):
        if not date_str:
            return Response({'detail': '缺少日期參數'}, status=400)

        dt = parse_date(date_str)
        if not dt:
            return Response({'detail': '日期格式錯誤，需 YYYY-MM-DD'}, status=400)

        qs = self.get_queryset()
        obj = None
        if self._has_field(Diary(), 'date'):
            try:
                obj = qs.get(date=dt)
            except Diary.DoesNotExist:
                return Response({'detail': 'not found'}, status=404)
        else:
            start = datetime(dt.year, dt.month, dt.day, 0, 0, 0, tzinfo=timezone.get_current_timezone())
            end = start + timedelta(days=1)
            obj = qs.filter(created_at__gte=start, created_at__lt=end).order_by('-created_at').first()
            if not obj:
                return Response({'detail': 'not found'}, status=404)

        data = {
            'id': obj.id,
            'date': (obj.date.isoformat() if self._has_field(obj, 'date') and obj.date else (obj.created_at or timezone.now()).date().isoformat()),
            'title': getattr(obj, 'title', None),
            'content': obj.content or '',
            'mood': getattr(obj, 'mood', None) or getattr(obj, 'emotion', None),
            'color': getattr(obj, 'mood_color', None),
            'icon': getattr(obj, 'weather_icon', None),
            'ai_analysis': getattr(obj, 'ai_message', None),
            'ai_message': getattr(obj, 'ai_message', None),
            'sentiment': getattr(obj, 'sentiment', None),
            'keywords': getattr(obj, 'keywords', None),
            'topics': getattr(obj, 'topics', None),
        }
        return Response(data, status=200)


# ===================== 照片 CRUD + 上傳 =====================

class PhotoViewSet(viewsets.ModelViewSet):
    authentication_classes = [authentication.TokenAuthentication]
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = PhotoSerializer
    parser_classes = [parsers.MultiPartParser, parsers.FormParser]

    def get_queryset(self):
        return Photo.objects.filter(owner=self.request.user).order_by('-uploaded_at')

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)
        try:
            update_achievement_progress(self.request.user, '2', increment=1.0)
        except Exception:
            pass

    @action(detail=False, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def upload(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(owner=request.user)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


# ===================== 成就 & 錢包（手動領取情緒餘額） =====================

class AchievementListView(APIView):
    """
    GET /api/achievements/
    回傳所有成就的狀態（手動領取版）
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        items = []
        for ach in Achievement.objects.all().order_by('is_daily', 'id'):
            status_dict = get_status(user, ach)  # {"claimable", "claimed_today", "unlocked"}
            items.append({
                "id": ach.id,
                "title": ach.achTitle,
                "desc": ach.achContent,
                "amount": ach.exp,           # 要發放的情緒餘額
                "is_daily": ach.is_daily,
                **status_dict,
            })
        return Response(items, status=200)


class AchievementClaimView(APIView):
    """
    POST /api/achievements/claim/
    body: {"id": "<achievement_id>"}
    依條件判斷是否可領，成功則寫入 ExpLog（情緒餘額入帳）
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        aid = (request.data.get('id') or '').strip()
        if not aid:
            return Response({"detail": "缺少成就 id"}, status=400)

        ach = Achievement.objects.filter(pk=aid).first()
        if not ach:
            return Response({"detail": "成就不存在"}, status=404)

        # 先看是否「已領」（用 get_status）
        pre = get_status(user, ach)
        if ach.is_daily and pre.get("claimed_today"):
            return Response({"detail": "今天已領取"}, status=409)
        if not ach.is_daily and pre.get("unlocked"):
            return Response({"detail": "已領取過"}, status=409)

        # 再確認是否可領
        if not is_claimable(user, ach):
            return Response({"detail": "尚未達成領取條件"}, status=400)

        ok, payload = claim_achievement(user, aid)
        if not ok:
            # payload = {"detail": "..."}
            return Response(payload, status=400)

        # payload = {"id", "amount", "balance", "status": {...}}
        return Response({"ok": True, **payload}, status=200)


class WalletView(APIView):
    """
    GET /api/wallet/
    回傳當前情緒餘額與最近流水
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        balance = current_balance(user)
        logs = (ExpLog.objects
                .filter(user=user)
                .order_by('-get_exp_time', '-id')[:30])

        recent = []
        for log in logs:
            recent.append({
                "time": (log.get_exp_time.astimezone(timezone.get_current_timezone())
                         if log.get_exp_time else timezone.now()).isoformat(),
                "delta": log.get_exp,
                "reason": log.reason,
                "balance": log.current_total,
            })

        return Response({
            "balance": balance,
            "recent": recent
        }, status=200)


# ===================== 今日備忘錄 / To-Do =====================

class TodoViewSet(viewsets.ModelViewSet):
    """
    /api/todos/
      - GET    /api/todos/?date=YYYY-MM-DD   只看當天（未帶 date 則回自己的全部）
      - POST   /api/todos/                   {title, date?, time?}
      - PATCH  /api/todos/{id}/              {is_done: true/false, ...}
      - DELETE /api/todos/{id}/
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = TodoSerializer

    def get_queryset(self):
        qs = Todo.objects.filter(user=self.request.user)

        # ?date=YYYY-MM-DD
        date_str = self.request.query_params.get('date')
        if date_str:
            try:
                day = datetime.fromisoformat(date_str).date()
            except ValueError:
                raise ValidationError({"date": "日期格式錯誤，需 YYYY-MM-DD"})
            qs = qs.filter(date=day)

        # 未完成在前 -> 時間（NULL 放最後）-> 建立時間
        return qs.order_by('is_done', F('time').asc(nulls_last=True), 'created_at')

    def perform_create(self, serializer):
        # user 從後端帶入；date 若未傳，TodoSerializer 會預設為今天
        serializer.save(user=self.request.user)
