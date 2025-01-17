from typing import Optional, List

import gym
import numpy as np
from flatland.core.env_observation_builder import ObservationBuilder
from flatland.envs.observations import TreeObsForRailEnv

from flatlander.envs.observations import Observation, register_obs
from flatlander.envs.observations.builders.done_removed_tree import DoneRemovedTreeObsForRailEnv
from flatlander.envs.observations.common.grouping_tree_flatter import GroupingTreeFlattener
from flatlander.envs.observations.common.predictors import get_predictor


@register_obs("tree")
class TreeObservation(Observation):

    def __init__(self, config) -> None:
        super().__init__(config)
        self._concat_agent_id = config.get('concat_agent_id', False)
        self._concat_status = config.get('concat_status', False)
        self._num_agents = config.get('num_agents', 5)
        self._builder = TreeObsForRailEnvRLLibWrapper(
            DoneRemovedTreeObsForRailEnv(
                max_depth=config['max_depth'],
                predictor=get_predictor(config=config)
            ),
            config.get('normalize_fixed', None),
            self._concat_agent_id,
            self._concat_status,
            self._num_agents
        )

    def builder(self) -> ObservationBuilder:
        return self._builder

    def observation_space(self) -> gym.Space:
        num_features_per_node = self._builder.observation_dim
        nr_nodes = 0
        for i in range(self.config['max_depth'] + 1):
            nr_nodes += np.power(4, i)
        dim = num_features_per_node * nr_nodes
        if self._concat_agent_id:
            dim += self._num_agents
        if self._concat_status:
            dim += 1
        return gym.spaces.Box(low=-1, high=1, shape=(dim,))


class TreeObsForRailEnvRLLibWrapper(ObservationBuilder):

    def __init__(self, tree_obs_builder: TreeObsForRailEnv,
                 normalize_fixed=None,
                 concat_agent_id=False,
                 concat_status=False,
                 num_agents=5):
        super().__init__()
        self._builder = tree_obs_builder
        self._concat_agent_id = concat_agent_id
        self._concat_status = concat_status
        self.tree_flatter = GroupingTreeFlattener(normalize_fixed=normalize_fixed,
                                                  num_agents=num_agents,
                                                  tree_depth=self._builder.max_depth,
                                                  builder=self._builder)

    @property
    def observation_dim(self):
        return self._builder.observation_dim

    def reset(self):
        self._builder.reset()

    def get(self, handle: int = 0):
        obs = self._builder.get(handle)
        norm_obs = self.tree_flatter.flatten(root=obs, handle=handle, concat_agent_id=self._concat_agent_id) \
            if obs is not None else None
        return norm_obs

    def get_many(self, handles: Optional[List[int]] = None):
        return {k: self.tree_flatter.flatten(root=o, handle=k,
                                             concat_status=self._concat_status,
                                             concat_agent_id=self._concat_agent_id)
                for k, o in self._builder.get_many(handles).items() if o is not None}

    def util_print_obs_subtree(self, tree):
        self._builder.util_print_obs_subtree(tree)

    def print_subtree(self, node, label, indent):
        self._builder.print_subtree(node, label, indent)

    def set_env(self, env):
        self._builder.set_env(env)
