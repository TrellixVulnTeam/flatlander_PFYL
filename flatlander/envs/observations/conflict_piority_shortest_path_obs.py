from typing import Optional, List

import gym
import numpy as np
from flatland.core.env_observation_builder import ObservationBuilder
from flatland.core.grid.grid4_utils import get_new_position
from flatland.core.grid.grid_utils import coordinate_to_position
from flatland.envs.agent_utils import RailAgentStatus
from flatland.envs.rail_env import RailEnv

from flatlander.algorithms.graph_coloring import GreedyGraphColoring, ShufflingGraphColoring
from flatlander.envs.observations import register_obs, Observation
from flatlander.envs.observations.common.predictors import get_predictor


@register_obs("shortest_path_priority_conflict")
class ConflictPriorityShortestPathObservation(Observation):

    def builder(self) -> ObservationBuilder:
        return self._builder

    def __init__(self, config) -> None:
        super().__init__(config)
        self._config = config if config is not None else {}
        self._builder = ConflictPriorityShortestPathObservationBuilder(
            predictor=get_predictor(config=config),
            encode_one_hot=True,
            asserts=self._config.get("asserts", False))

    def observation_space(self) -> gym.Space:
        return gym.spaces.Tuple((gym.spaces.Box(low=0, high=1, shape=(14,)),
                                 gym.spaces.discrete.Discrete(2)))


class ConflictPriorityShortestPathObservationBuilder(ObservationBuilder):
    def reset(self):
        self._shortest_path_conflict_map = {}
        self._other_path_conflict_map = {}
        self._prev_shortest_path_conflict_map = {}
        self._prev_other_path_conflict_map = {}
        self._prev_sp_prios = {}
        self._prev_other_prios = {}

    def set_env(self, env):
        self.predictor.set_env(env)
        self.env = env

    def __init__(self, predictor=None, encode_one_hot=True, asserts=False):
        super().__init__()
        self._shortest_path_conflict_map = {}
        self._other_path_conflict_map = {}
        self._prev_shortest_path_conflict_map = {}
        self._prev_other_path_conflict_map = {}
        self._prev_sp_prios = {}
        self._prev_other_prios = {}
        self.predictor = predictor
        self._directions = list(range(4))
        self._path_size = len(self._directions) + 3
        self._encode_one_hot = encode_one_hot
        self._asserts = asserts

    def get_many(self, handles: Optional[List[int]] = None):

        self._shortest_path_conflict_map = {handle: [] for handle in handles}
        self._other_path_conflict_map = {handle: [] for handle in handles}

        if self.predictor:
            self.max_prediction_depth = 0
            self.predicted_pos = {}
            self.predicted_dir = {}
            self.predictions = self.predictor.get()
            if self.predictions:
                for t in range(self.predictor.max_depth + 1):
                    pos_list = []
                    dir_list = []
                    for a in handles:
                        if self.predictions[a] is None:
                            continue
                        pos_list.append(self.predictions[a][t][1:3])
                        dir_list.append(self.predictions[a][t][3])
                    self.predicted_pos.update({t: coordinate_to_position(self.env.width, pos_list)})
                    self.predicted_dir.update({t: dir_list})
                self.max_prediction_depth = len(self.predicted_pos)
        # Update local lookup table for all agents' positions
        # ignore other agents not in the grid (only status active and done)
        # self.location_has_agent = {tuple(agent.position): 1 for agent in self.env.agents if
        #                         agent.status in [RailAgentStatus.ACTIVE, RailAgentStatus.DONE]}

        self.location_has_agent = {}
        self.location_has_agent_direction = {}
        self.location_has_agent_speed = {}
        self.location_has_agent_malfunction = {}
        self.location_has_agent_ready_to_depart = {}

        for _agent in self.env.agents:
            if _agent.status in [RailAgentStatus.ACTIVE, RailAgentStatus.DONE] and \
                    _agent.position:
                self.location_has_agent[tuple(_agent.position)] = 1
                self.location_has_agent_direction[tuple(_agent.position)] = _agent.direction
                self.location_has_agent_speed[tuple(_agent.position)] = _agent.speed_data['speed']
                self.location_has_agent_malfunction[tuple(_agent.position)] = _agent.malfunction_data[
                    'malfunction']

            if _agent.status in [RailAgentStatus.READY_TO_DEPART] and \
                    _agent.initial_position:
                self.location_has_agent_ready_to_depart[tuple(_agent.initial_position)] = \
                    self.location_has_agent_ready_to_depart.get(tuple(_agent.initial_position), 0) + 1

        self._conflict_map = {handle: [] for handle in handles}
        obs_dict = {handle: self.get(handle) for handle in handles}

        # the order of the colors matters
        sp_priorities = GreedyGraphColoring.color(colors=[1, 0],
                                                  nodes=obs_dict.keys(),
                                                  neighbors=self._shortest_path_conflict_map)

        op_priorities = GreedyGraphColoring.color(colors=[1, 0],
                                                  nodes=obs_dict.keys(),
                                                  neighbors=self._other_path_conflict_map)
        for handle, obs in obs_dict.items():
            if obs is not None:
                obs[0][6] = sp_priorities[handle]
                obs[0][13] = op_priorities[handle]

        if self._asserts:
            assert [sp_priorities[h] != [sp_priorities[ch] for ch in chs]
                    for h, chs in self._shortest_path_conflict_map.items()]
            assert [op_priorities[h] != [op_priorities[ch] for ch in chs]
                    for h, chs in self._other_path_conflict_map.items()]

        self._prev_sp_prios = sp_priorities
        self._prev_other_prios = op_priorities
        self._prev_other_path_conflict_map = self._other_path_conflict_map
        self._prev_shortest_path_conflict_map = self._shortest_path_conflict_map

        return obs_dict

    def get(self, handle: int = 0):
        self.env: RailEnv = self.env
        agent = self.env.agents[handle]
        if agent.status == RailAgentStatus.READY_TO_DEPART:
            agent_virtual_position = agent.initial_position
        elif agent.status == RailAgentStatus.ACTIVE:
            agent_virtual_position = agent.position
        elif agent.status == RailAgentStatus.DONE:
            agent_virtual_position = agent.target
        else:
            return None

        possible_transitions = self.env.rail.get_transitions(*agent_virtual_position, agent.direction)
        distance_map = self.env.distance_map.get()
        nan_inf_mask = ((distance_map != np.inf) * (np.abs(np.isnan(distance_map) - 1))).astype(np.bool)
        max_distance = np.max(distance_map[nan_inf_mask])
        assert not np.isnan(max_distance)
        assert max_distance != np.inf
        possible_steps = []

        # look in all directions for possible moves
        for movement in self._directions:
            if possible_transitions[movement]:
                next_move = movement
                pos = get_new_position(agent_virtual_position, movement)
                distance = distance_map[agent.handle][pos + (movement,)]
                distance = max_distance if (
                        distance == np.inf or np.isnan(distance)) else distance

                cell_transitions = self.env.rail.get_transitions(*pos, movement)
                _, ch = self.detect_conflicts(1,
                                              np.reciprocal(agent.speed_data["speed"]),
                                              pos,
                                              cell_transitions,
                                              handle,
                                              movement)

                conflict = ch is not None

                if conflict and len(possible_steps) == 0:
                    self._shortest_path_conflict_map[handle].append(ch)
                elif conflict:
                    self._other_path_conflict_map[handle].append(ch)

                if self._encode_one_hot:
                    next_move_one_hot = np.zeros(len(self._directions))
                    next_move_one_hot[next_move] = 1
                    next_move = next_move_one_hot

                possible_steps.append((next_move, [distance / max_distance],
                                       [int(conflict)],
                                       [int(not conflict)]))  # priority field

        possible_steps = sorted(possible_steps, key=lambda step: step[1])
        obs = np.full(self._path_size * 2, fill_value=0)
        for i, path in enumerate(possible_steps):
            obs[i * self._path_size:self._path_size * (i + 1)] = np.concatenate([arr for arr in path])

        return obs, int(agent.status.value != RailAgentStatus.READY_TO_DEPART)

    def _reverse_dir(self, direction):
        return int((direction + 2) % 4)

    def detect_conflicts(self, tot_dist,
                         time_per_cell,
                         position,
                         cell_transitions,
                         handle,
                         direction):

        potential_conflict = np.inf
        conflict_handle = None
        predicted_time = int(tot_dist * time_per_cell)
        while self.predictor and predicted_time < self.max_prediction_depth:
            predicted_time = int(tot_dist * time_per_cell)
            int_position = coordinate_to_position(self.env.width, [position])
            if tot_dist < self.max_prediction_depth:

                pre_step = max(0, predicted_time - 1)
                post_step = min(self.max_prediction_depth - 1, predicted_time + 1)

                # Look for conflicting paths at distance tot_dist
                if int_position in np.delete(self.predicted_pos[predicted_time], handle, 0):
                    conflicting_agent = np.where(self.predicted_pos[predicted_time] == int_position)
                    for ca in conflicting_agent[0]:
                        if direction != self.predicted_dir[predicted_time][ca] and cell_transitions[
                            self._reverse_dir(
                                self.predicted_dir[predicted_time][ca])] == 1 and tot_dist < potential_conflict:
                            potential_conflict = tot_dist
                            conflict_handle = ca
                        if self.env.agents[ca].status == RailAgentStatus.DONE and tot_dist < potential_conflict:
                            potential_conflict = tot_dist
                            conflict_handle = ca

                # Look for conflicting paths at distance num_step-1
                elif int_position in np.delete(self.predicted_pos[pre_step], handle, 0):
                    conflicting_agent = np.where(self.predicted_pos[pre_step] == int_position)
                    for ca in conflicting_agent[0]:
                        if direction != self.predicted_dir[pre_step][ca] \
                                and cell_transitions[self._reverse_dir(self.predicted_dir[pre_step][ca])] == 1 \
                                and tot_dist < potential_conflict:  # noqa: E125
                            potential_conflict = tot_dist
                            conflict_handle = ca
                        if self.env.agents[ca].status == RailAgentStatus.DONE and tot_dist < potential_conflict:
                            potential_conflict = tot_dist
                            conflict_handle = ca

                # Look for conflicting paths at distance num_step+1
                elif int_position in np.delete(self.predicted_pos[post_step], handle, 0):
                    conflicting_agent = np.where(self.predicted_pos[post_step] == int_position)
                    for ca in conflicting_agent[0]:
                        if direction != self.predicted_dir[post_step][ca] and cell_transitions[self._reverse_dir(
                                self.predicted_dir[post_step][ca])] == 1 \
                                and tot_dist < potential_conflict:  # noqa: E125
                            potential_conflict = tot_dist
                            conflict_handle = ca
                        if self.env.agents[ca].status == RailAgentStatus.DONE and tot_dist < potential_conflict:
                            potential_conflict = tot_dist
                            conflict_handle = ca
            tot_dist += 1
            position, direction = self.get_shortest_path_position(position=position, direction=direction, handle=handle)

        return potential_conflict, conflict_handle

    def get_shortest_path_position(self, position, direction, handle):
        distance_map = self.env.distance_map.get()
        nan_inf_mask = ((distance_map != np.inf) * (np.abs(np.isnan(distance_map) - 1))).astype(np.bool)
        max_dist = np.max(self.env.distance_map.get()[nan_inf_mask])

        possible_transitions = self.env.rail.get_transitions(*position, direction)
        min_dist = np.inf
        sp_move = None
        sp_pos = None

        for movement in self._directions:
            if possible_transitions[movement]:
                pos = get_new_position(position, movement)
                distance = self.env.distance_map.get()[handle][pos + (movement,)]
                distance = max_dist if (distance == np.inf or np.isnan(distance)) else distance
                if distance <= min_dist:
                    min_dist = distance
                    sp_move = movement
                    sp_pos = pos

        return sp_pos, sp_move
