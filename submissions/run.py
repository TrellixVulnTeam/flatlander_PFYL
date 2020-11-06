import os
from copy import deepcopy

from flatlander.agents.shortest_path_agent import ShortestPathAgent
from flatlander.envs.utils.priorization.priorizer import NrAgentsSameStart, DistToTargetPriorizer
import numpy as np

os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
os.environ["CUDA_VISIBLE_DEVICES"] = "-1"

from collections import defaultdict
from flatlander.envs.utils.robust_gym_env import RobustFlatlandGymEnv
from flatland.evaluators.client import FlatlandRemoteClient, TimeoutException
from flatlander.envs.observations import make_obs
from flatlander.submission.helper import episode_start_info, episode_end_info, init_run, get_agent
from time import time
import tensorflow as tf

tf.compat.v1.disable_eager_execution()
remote_client = FlatlandRemoteClient()

TIME_LIMIT = 60 * 60 * 8
EXPLORE = False


def skip(done):
    print("Skipping episode")
    while not done['__all__']:
        observation, all_rewards, done, info = remote_client.env_step({})
        print('!', end='', flush=True)


def evaluate(config, run):
    start_time = time()
    obs_builder = make_obs(config["env_config"]['observation'],
                           config["env_config"].get('observation_config')).builder()
    evaluation_number = 0
    total_reward = 0
    all_rewards = []
    prio_agent = get_agent(config, run)
    sp_agent = ShortestPathAgent()
    num_explorations = 3

    while True:
        try:
            observation, info = remote_client.env_create(obs_builder_object=obs_builder)

            if not observation:
                break

            steps = 0

            evaluation_number += 1
            episode_start_info(evaluation_number, remote_client=remote_client)
            robust_env = RobustFlatlandGymEnv(rail_env=remote_client.env,
                                              max_nr_active_agents=100,
                                              observation_space=None,
                                              priorizer=NrAgentsSameStart(),
                                              allow_noop=True)

            priorities = prio_agent.compute_actions(observation, explore=False)
            sorted_actions = {k: v for k, v in
                              sorted(priorities.items(), key=lambda item: item[1], reverse=True)}
            sorted_handles = list(sorted_actions.keys())

            priorizations = []

            if remote_client.env.get_num_agents() <= 5 and EXPLORE:
                for i in range(num_explorations):
                    obs = observation
                    if i != 0:
                        priorities = prio_agent.compute_actions(obs, explore=True)
                        sorted_actions = {k: v for k, v in
                                          sorted(priorities.items(), key=lambda item: item[1], reverse=True)}
                        sorted_handles = list(sorted_actions.keys())
                    env = deepcopy(remote_client.env)
                    ep_return = 0
                    done = defaultdict(lambda: False)

                    print("Explore priorizations step", i + 1)

                    while not done['__all__']:
                        actions = ShortestPathAgent().compute_actions(obs, env)
                        robust_actions = robust_env.get_robust_actions(actions, sorted_handles)
                        obs, all_rewards, done, info = env.step(robust_actions)
                        steps += 1
                        ep_return += np.sum(list(all_rewards.values()))

                    priorizations.append((ep_return, sorted_handles))

            if len(priorizations) > 0:
                sorted_handles = max(priorizations, key=lambda t: t[0])[1]

            done = defaultdict(lambda: False)
            while True:
                try:
                    while not done['__all__']:
                        rail_actions = sp_agent.compute_actions(observation, remote_client.env)
                        robust_actions = robust_env.get_robust_actions(rail_actions, sorted_handles=sorted_handles)

                        observation, all_rewards, done, info = remote_client.env_step(robust_actions)
                        steps += 1
                        print('.', end='', flush=True)

                        if (time() - start_time) > TIME_LIMIT:
                            skip(done)
                            break

                    if done['__all__']:
                        total_reward = episode_end_info(all_rewards,
                                                        total_reward,
                                                        evaluation_number,
                                                        steps, remote_client=remote_client)
                        break

                except TimeoutException as err:
                    print("Timeout! Will skip this episode and go to the next.", err)
                    break
        except TimeoutException as err:
            print("Timeout during planning time. Will skip to next evaluation!", err)

    print("Evaluation of all environments complete...")
    print(remote_client.submit())


if __name__ == "__main__":
    config, run = init_run()
    evaluate(config, run)
