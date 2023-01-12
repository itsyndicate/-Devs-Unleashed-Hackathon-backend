from django.db.models import Q
from rest_framework import serializers

from core.business_services.notification_sender import send_fight_call_notification
from core.models import Taskogotchi, Project, PlayerProfile, FightChallenge, Player, FightStatus
from django.shortcuts import get_object_or_404
from core.business_services.fight_status_state_machine import FightStatusStateMachine


class ProjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = ('id', 'name', 'project_id')


class PlayerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Player
        fields = ('id', 'name', 'account_id', 'email')


class CreatePlayerProfileSerializer(serializers.Serializer):
    player_name = serializers.CharField(max_length=255)
    account_id = serializers.CharField(max_length=255)
    project_id = serializers.CharField(max_length=255)
    project_name = serializers.CharField(max_length=255)


class PlayerProfileSerializer(serializers.ModelSerializer):
    player = PlayerSerializer()
    project = ProjectSerializer()

    class Meta:
        model = PlayerProfile
        fields = ('id', 'player', 'project',)


class OpponentSerializer(serializers.ModelSerializer):
    profile = PlayerProfileSerializer()
    in_fight = serializers.SerializerMethodField('is_in_fight', read_only=True)

    def is_in_fight(self, obj: Taskogotchi) -> bool:
        return FightChallenge.objects.filter(Q(opponent=obj.profile) | Q(initiator=obj.profile)) \
            .exclude(status__in=[FightStatus.COMPLETED, FightStatus.CANCELED]).exists()

    class Meta:
        model = Taskogotchi
        fields = ('id', 'profile', 'in_fight', 'health', 'strength')


class CreateFightChallengeSerializer(serializers.Serializer):
    project_id = serializers.CharField(required=True)
    account_id = serializers.CharField(required=True)
    opponent_id = serializers.CharField(required=True)


class UpdateFightChallengeSerializer(serializers.Serializer):
    project_id = serializers.CharField(required=True)
    account_id = serializers.CharField(required=True)
    action = serializers.CharField(required=True)
    winner_account_id = serializers.CharField(required=False)


class FightChallengeSerializer(serializers.ModelSerializer):
    initiator = PlayerProfileSerializer(read_only=True)
    initiator_health = serializers.IntegerField(read_only=True)
    initiator_strength = serializers.IntegerField(read_only=True)
    opponent = PlayerProfileSerializer(read_only=True)
    opponent_health = serializers.IntegerField(read_only=True)
    opponent_strength = serializers.IntegerField(read_only=True)
    winner = PlayerProfileSerializer(required=False)
    status_description = serializers.CharField(source='get_status_display', read_only=True)
    status = serializers.CharField(read_only=True)
    account_id = serializers.CharField(write_only=True)
    project_id = serializers.CharField(write_only=True)
    opponent_id = serializers.CharField(write_only=True, required=False)
    winner_account_id = serializers.CharField(write_only=True, required=False)
    action = serializers.CharField(write_only=True, required=False)

    def filter_validated_data(self, instance, validated_data):
        """Filters validated_data to contain only fields that are included in model"""
        field_names = [field.name for field in instance._meta.get_fields()]
        return {k: v for k, v in validated_data.items() if k in field_names}

    def create(self, validated_data):
        account_id = validated_data.pop('account_id')
        project_id = validated_data.pop('project_id')
        opponent_id = validated_data.pop('opponent_id')
        initiator_profile = get_object_or_404(PlayerProfile, player__account_id=account_id,
                                              project__project_id=project_id)
        opponent_profile = get_object_or_404(PlayerProfile, player__account_id=opponent_id,
                                             project__project_id=project_id)
        validated_data['initiator'] = initiator_profile
        validated_data['opponent'] = opponent_profile
        validated_data['status'] = FightStatus.WAITING_ACCEPT
        validated_data['initiator_health'] = initiator_profile.taskogotchi.health
        validated_data['initiator_strength'] = initiator_profile.taskogotchi.strength
        validated_data['opponent_health'] = opponent_profile.taskogotchi.health
        validated_data['opponent_strength'] = opponent_profile.taskogotchi.strength
        validated_data = self.filter_validated_data(FightChallenge(), validated_data)
        result = super().create(validated_data)
        send_fight_call_notification(result)
        return result

    def update(self, instance: FightChallenge, validated_data):
        action = validated_data.pop('action', None)
        if action == 'complete':
            if (winner_account_id := validated_data.pop('winner_account_id', None)) is not None:
                if winner_account_id not in [instance.initiator.player.account_id, instance.opponent.player.account_id]:
                    raise serializers.ValidationError(
                        detail="winner_account_id must be either initiator or opponent account_id")
                winner_profile = get_object_or_404(PlayerProfile, player__account_id=winner_account_id,
                                                   project=instance.initiator.project)
                validated_data['winner'] = winner_profile
                validated_data['draw'] = False
            else:
                validated_data['draw'] = True

        try:
            instance = FightStatusStateMachine.process_action(action, instance, save=False)
        except ValueError as e:
            raise serializers.ValidationError(str(e))
        validated_data = self.filter_validated_data(FightChallenge(), validated_data)
        return super().update(instance, validated_data)

    class Meta:
        model = FightChallenge
        fields = ('id', 'initiator', 'initiator_health', 'initiator_strength', 'opponent', 'opponent_health',
                  'opponent_strength', 'status', 'status_description', 'winner', 'draw', 'account_id', 'project_id',
                  'opponent_id', 'action', 'winner_account_id')


class TaskogotchiSerializer(serializers.ModelSerializer):
    profile = PlayerProfileSerializer(read_only=True)
    account_id = serializers.CharField(write_only=True)
    project_id = serializers.CharField(write_only=True)
    last_updated = serializers.DateTimeField(read_only=True)

    def create(self, validated_data):
        player_profile = get_object_or_404(PlayerProfile, player__account_id=validated_data.pop('account_id'),
                                           project__project_id=validated_data.pop('project_id'))
        validated_data['profile'] = player_profile
        return super().create(validated_data)

    class Meta:
        model = Taskogotchi
        fields = ('id', 'profile', 'image', 'last_updated', 'health', 'strength', 'account_id', 'project_id')
