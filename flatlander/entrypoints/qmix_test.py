"""The two-step game from QMIX: https://arxiv.org/pdf/1803.11485.pdf
Configurations you can try:
    - normal policy gradients (PG)
    - contrib/MADDPG
    - QMIX
See also: centralized_critic.py for centralized critic PPO on this game.
"""

import argparse

import ray
from gym.spaces import Tuple
from ray import tune
from ray.tune import register_env, grid_search

from flatlander.envs.flatland_sparse import FlatlandSparse
from flatlander.envs.observations import make_obs
from flatlander.envs.utils.gym_env import FlatlandGymEnv

parser = argparse.ArgumentParser()
parser.add_argument("--run", type=str, default="QMIX")
parser.add_argument("--num-cpus", type=int, default=0)
parser.add_argument("--as-test", action="store_true")
parser.add_argument("--torch", action="store_true")
parser.add_argument("--stop-timesteps", type=int, default=50000)

if __name__ == "__main__":
    args = parser.parse_args()

    grouping = {
        "group_1": [0, 1, 2, 3, 4],
    }
    obs_space = Tuple([make_obs("tree", {"max_depth": 2, "shortest_path_max_depth": 30}).observation_space()
                       for i in range(5)])

    act_space = Tuple([FlatlandGymEnv.action_space for i in range(5)])

    register_env(
        "flatland_sparse_grouped",
        lambda config: FlatlandSparse(config).with_agent_groups(
            grouping, obs_space=obs_space, act_space=act_space))

    config = {
        "rollout_fragment_length": 50,
        "train_batch_size": 1000,
        "exploration_config": {
            "epsilon_timesteps": 5000,
            "final_epsilon": 0.05,
        },
        "num_workers": 0,
        "num_gpus": 1,
        "num_envs_per_worker": 1,
        "mixer": "qmix",
        "env_config": {
            "observation": "tree",
            "observation_config": {"max_depth": 2,
                                   "shortest_path_max_depth": 30,
                                   "small_tree": False},
            "generator": "sparse_rail_generator",
            "generator_config": "small_v0",
            "global_reward": True,
            "gym_env": "fill_missing"
        },
    }

    ray.init(num_cpus=args.num_cpus or None)

    stop = {
        "timesteps_total": args.stop_timesteps,
    }

    config = dict(config, **{
        "env": "flatland_sparse_grouped",
    })

    results = tune.run(args.run, stop=stop, config=config, verbose=1)

    ray.shutdown()
