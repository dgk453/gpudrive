import wandb
import yaml
from box import Box
from typing import Callable
from datetime import datetime
import dataclasses
from integrations.rl.sb3.ppo.ippo import IPPO
from integrations.rl.sb3.callbacks import MultiAgentCallback
from pygpudrive.env.config import EnvConfig, SceneConfig
from pygpudrive.env.wrappers.sb3_wrapper import SB3MultiAgentEnv

from networks.perm_eq_late_fusion import LateFusionNet, LateFusionPolicy
from networks.basic_ffn import FFN, FeedForwardPolicy
from pygpudrive.env.config import SelectionDiscipline


def linear_schedule(initial_value: float) -> Callable[[float], float]:
    """Linear learning rate schedule."""

    def func(progress_remaining: float) -> float:
        return progress_remaining * initial_value

    return func


def load_config(config_path):
    """Load the configuration file."""
    with open(config_path, "r") as f:
        return Box(yaml.safe_load(f))


def train(exp_config: Box, scene_config: SceneConfig):
    """Run PPO training with stable-baselines3."""

    env_config = dataclasses.replace(
        EnvConfig(),
        reward_type=exp_config.reward_type,
        collision_weight=exp_config.collision_weight,
        goal_achieved_weight=exp_config.goal_achieved_weight,
        off_road_weight=exp_config.off_road_weight,
        episode_len=exp_config.episode_len,
        remove_non_vehicles=exp_config.remove_non_vehicles,
        polyline_reduction_threshold=exp_config.polyline_reduction_threshold,
        obs_radius=exp_config.observation_radius,
    )

    # Select model
    if exp_config.mlp_class == "late_fusion":
        exp_config.mlp_class = LateFusionNet
        exp_config.policy = LateFusionPolicy
    elif exp_config.mlp_class == "feed_forward":
        exp_config.mlp_class = FFN
        exp_config.policy = FeedForwardPolicy
    else:
        raise NotImplementedError(
            f"Unsupported MLP class: {exp_config.mlp_class}"
        )

    # Make environment
    env = SB3MultiAgentEnv(
        config=env_config,
        scene_config=scene_config,
        exp_config=exp_config,
        max_cont_agents=env_config.max_num_agents_in_scene,
        device=exp_config.device,
    )

    exp_config.batch_size = (
        exp_config.num_worlds * exp_config.n_steps
    ) // exp_config.num_minibatches

    datetime_ = datetime.now().strftime("%m_%d_%H_%S")
    run_id = f"SB3_{datetime_}_{exp_config.k_unique_scenes}scenes"
    run = wandb.init(
        project=exp_config.project_name,
        name=run_id,
        id=run_id,
        group=exp_config.group_name,
        sync_tensorboard=exp_config.sync_tensorboard,
        tags=exp_config.tags,
        mode=exp_config.wandb_mode,
        config={**exp_config, **env_config.__dict__},
    )

    custom_callback = MultiAgentCallback(
        config=exp_config,
        wandb_run=run if run_id is not None else None,
    )

    model = IPPO(
        n_steps=exp_config.n_steps,
        batch_size=exp_config.batch_size,
        env=env,
        seed=exp_config.seed,
        verbose=exp_config.verbose,
        device=exp_config.device,
        tensorboard_log=f"runs/{run_id}" if run_id is not None else None,
        mlp_class=exp_config.mlp_class,
        policy=exp_config.policy,
        gamma=exp_config.gamma,
        gae_lambda=exp_config.gae_lambda,
        vf_coef=exp_config.vf_coef,
        clip_range=exp_config.clip_range,
        learning_rate=linear_schedule(exp_config.lr),
        ent_coef=exp_config.ent_coef,
        n_epochs=exp_config.n_epochs,
        env_config=env_config,
        exp_config=exp_config,
    )

    model.learn(
        total_timesteps=exp_config.total_timesteps,
        callback=custom_callback,
    )

    run.finish()
    env.close()


if __name__ == "__main__":

    exp_config = load_config("baselines/ippo/config/ippo_ff_sb3.yaml")

    scene_config = SceneConfig(
        path=exp_config.data_dir,
        num_scenes=exp_config.num_worlds,
        discipline=SelectionDiscipline.K_UNIQUE_N
        if exp_config.selection_discipline == "K_UNIQUE_N"
        else SelectionDiscipline.PAD_N,
        k_unique_scenes=exp_config.k_unique_scenes,
    )

    train(exp_config, scene_config)