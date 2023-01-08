from django.urls import path
from .views import RegisterPlayerView, TaskogotchiView, OpponentsListView, FightChallengeView

urlpatterns = [
    path('register-player', RegisterPlayerView.as_view(), name='register-player'),
    path('taskogotchi', TaskogotchiView.as_view(), name='taskogotchi'),
    path('available-opponents', OpponentsListView.as_view(), name='available-opponents'),
    path('fight', FightChallengeView.as_view(), name='fight'),
]
