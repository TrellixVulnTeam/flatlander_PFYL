from typing import Optional, List

import gym
import numpy as np

from flatland.core.env_observation_builder import ObservationBuilder
from flatland.envs.observations import TreeObsForRailEnv
from flatland.envs.predictions import ShortestPathPredictorForRailEnv
from flatland.envs.rail_env import RailEnvActions
from flatlander.envs.observations import Observation, register_obs
from flatlander.envs.observations.utils import norm_obs_clip
from flatlander.envs.utils.const import NUMBER_ACTIONS


@register_obs("fixed_tree")
class FixedTreeObservation(Observation):

    def __init__(self, config) -> None:
        super().__init__(config)
        self._builder = FixedTreeObsWrapper(
            TreeObsForRailEnv(
                max_depth=config['max_depth'],
                predictor=ShortestPathPredictorForRailEnv(config['shortest_path_max_depth'])
            )
        )

    def builder(self) -> ObservationBuilder:
        return self._builder

    def observation_space(self) -> gym.Space:
        return gym.spaces.Box(low=-np.inf, high=np.inf, shape=(self._builder.max_nr_nodes,
                                                               self._builder.observation_dim,))


class FixedTreeObsWrapper(ObservationBuilder):

    def __init__(self, tree_obs_builder: TreeObsForRailEnv):
        super().__init__()
        self._builder = tree_obs_builder
        self._positional_encoding_len = self._builder.max_depth * NUMBER_ACTIONS
        self._max_nr_nodes = 0
        self._available_actions = [RailEnvActions.MOVE_FORWARD,
                                   RailEnvActions.DO_NOTHING,
                                   RailEnvActions.MOVE_LEFT,
                                   RailEnvActions.MOVE_RIGHT]
        for i in range(self._builder.max_depth + 1):
            self._max_nr_nodes += np.power(4, i)

    @property
    def observation_dim(self):
        return self._builder.observation_dim

    @property
    def max_nr_nodes(self):
        return self._max_nr_nodes

    def reset(self):
        self._builder.reset()

    def get(self, handle: int = 0):
        obs: TreeObsForRailEnv.Node = self._builder.get(handle)
        return self._build_pairs(obs)

    def _build_pairs(self, obs_node: TreeObsForRailEnv.Node):
        node_observations = []
        self.dfs(obs_node, node_observations)
        node_observations = np.array(node_observations)
        padded_observations = np.full(shape=(self.max_nr_nodes, self.observation_dim,), fill_value=-np.inf)
        padded_observations[:len(node_observations)] = node_observations
        return padded_observations

    def get_many(self, handles: Optional[List[int]] = None):
        result = {k: self._build_pairs(o)
                  for k, o in self._builder.get_many(handles).items() if o is not None}
        return result

    def set_env(self, env):
        self._builder.set_env(env)

    @staticmethod
    def _get_node_feature_vector(node: TreeObsForRailEnv.Node) -> np.ndarray:
        data = np.zeros(6)
        distance = np.zeros(1)
        agent_data = np.zeros(4)

        data[0] = node.dist_own_target_encountered
        data[1] = node.dist_other_target_encountered
        data[2] = node.dist_other_agent_encountered
        data[3] = node.dist_potential_conflict
        data[4] = node.dist_unusable_switch
        data[5] = node.dist_to_next_branch

        distance[0] = node.dist_min_to_target

        agent_data[0] = node.num_agents_same_direction
        agent_data[1] = node.num_agents_opposite_direction
        agent_data[2] = node.num_agents_malfunctioning
        agent_data[3] = node.speed_min_fractional

        data = norm_obs_clip(data, fixed_radius=10)
        distance = norm_obs_clip(distance, normalize_to_range=True)
        agent_data = np.clip(agent_data, -1, 1)
        normalized_obs = np.concatenate([data, distance, agent_data])

        return normalized_obs

    def dfs(self, node: TreeObsForRailEnv.Node,
            node_observations: list):
        """
        Depth first search, as operation should be used the inference
        :param node_observations: accumulated obs vectors of nodes
        :param node: current node
        """
        for action in self._available_actions:
            filtered = list(filter(lambda k: k == RailEnvActions.to_char(action.value), node.childs.keys()))
            if len(filtered) == 1 and not isinstance(node.childs[filtered[0]], float):
                self.dfs(node.childs[filtered[0]], node_observations)

        node_observations.append(self._get_node_feature_vector(node))
