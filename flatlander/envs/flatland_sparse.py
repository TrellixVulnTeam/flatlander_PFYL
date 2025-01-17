import logging
from pprint import pprint

import gym

from flatland.envs.malfunction_generators import ParamMalfunctionGen, \
    NoMalfunctionGen, MalfunctionParameters
from flatland.envs.persistence import RailEnvPersister
from flatland.envs.rail_generators import sparse_rail_generator, complex_rail_generator
from flatland.envs.schedule_generators import sparse_schedule_generator
from flatlander.envs import get_generator_config
from flatlander.envs.flatland_base import FlatlandBase
from flatlander.envs.observations import make_obs
from flatlander.envs.utils.global_gym_env import GlobalFlatlandGymEnv
from flatlander.envs.utils.gym_env import FlatlandGymEnv
from flatlander.envs.utils.gym_env_fill_missing import FillingFlatlandGymEnv
from flatlander.envs.utils.gym_env_wrappers import AvailableActionsWrapper, SkipNoChoiceCellsWrapper, \
    SparseRewardWrapper, \
    DeadlockWrapper, ShortestPathActionWrapper, DeadlockResolutionWrapper, GlobalRewardWrapper, \
    NoStopShortestPathActionWrapper, PriorizationWrapper, SparsePriorizationWrapper
from flatlander.envs.utils.gym_env_wrappers import FlatlandRenderWrapper as RailEnv
from flatlander.envs.utils.robust_gym_env import RobustFlatlandGymEnv
from flatlander.envs.utils.seq_schedule_generator import SequentialSparseSchedGen
from flatlander.envs.utils.sequential_gym_env import SequentialFlatlandGymEnv


class FlatlandSparse(FlatlandBase):
    _gym_envs = {"default": FlatlandGymEnv,
                 "fill_missing": FillingFlatlandGymEnv,
                 "sequential": SequentialFlatlandGymEnv,
                 "robust": RobustFlatlandGymEnv,
                 "global": GlobalFlatlandGymEnv}

    _sp_action_needed = ["priority_path", 'shortest_path', 'shortest_path_priority_conflict']

    def __init__(self, env_config, fine_tune_env_path=None, max_steps=None, **kwargs) -> None:
        super().__init__(env_config.get("actions_are_logits", False), max_steps=max_steps)

        assert env_config['generator'] == 'sparse_rail_generator'
        self._env_config = env_config
        self._fine_tune_env_path = fine_tune_env_path

        self._observation = make_obs(env_config['observation'], env_config.get('observation_config'))
        self._config = get_generator_config(env_config['generator_config'])

        if env_config.get('number_of_agents', None) is not None:
            self._config['number_of_agents'] = env_config['number_of_agents']

        # Overwrites with env_config seed if it exists
        if env_config.get('seed'):
            self._config['seed'] = env_config.get('seed')

        if not hasattr(env_config, 'worker_index') or (env_config.worker_index == 0 and env_config.vector_index == 0):
            print("=" * 50)
            pprint(self._config)
            print("=" * 50)

        self._gym_env_class = self._gym_envs[env_config.get("gym_env", "default")]

        self._env = self._gym_env_class(
            rail_env=self._launch(),
            observation_space=self._observation.observation_space(),
            render=env_config.get('render'),
            regenerate_rail_on_reset=self._config['regenerate_rail_on_reset'],
            regenerate_schedule_on_reset=self._config['regenerate_schedule_on_reset'],
            config=env_config,
            allow_noop=env_config.get('allow_noop', True)
        )

        if env_config['observation'] in self._sp_action_needed:
            self._env = ShortestPathActionWrapper(self._env)
        if env_config['observation'] == 'path' or env_config['observation'] == 'nr_conflicts_path':
            self._env = NoStopShortestPathActionWrapper(self._env)
        if env_config.get('priorization', False):
            self._env = PriorizationWrapper(self._env)
        if env_config.get('sparse_priorization', False):
            self._env = SparsePriorizationWrapper(self._env)
        if env_config.get('sparse_reward', False):
            self._env = SparseRewardWrapper(self._env, finished_reward=env_config.get('done_reward', 1),
                                            not_finished_reward=env_config.get('not_finished_reward', -1))
        if env_config.get('global_reward', False):
            self._env = GlobalRewardWrapper(self._env)
        if env_config.get('deadlock_reward', 0) != 0:
            self._env = DeadlockWrapper(self._env, deadlock_reward=env_config['deadlock_reward'])
        if env_config.get('resolve_deadlocks', False):
            deadlock_reward = env_config.get('deadlock_reward', 0)
            self._env = DeadlockResolutionWrapper(self._env, deadlock_reward)
        if env_config.get('skip_no_choice_cells', False):
            self._env = SkipNoChoiceCellsWrapper(self._env, env_config.get('accumulate_skipped_rewards', False),
                                                 discounting=env_config.get('discounting', 1.))
        if env_config.get('available_actions_obs', False):
            self._env = AvailableActionsWrapper(self._env, env_config.get('allow_noop', True))
        if env_config.get('fill_unavailable_actions', False):
            self._env = AvailableActionsWrapper(self._env, env_config.get('allow_noop', True))

    @property
    def observation_space(self) -> gym.spaces.Space:
        return self._env.observation_space

    @property
    def action_space(self) -> gym.spaces.Space:
        return self._env.action_space

    def get_rail_generator(self):
        rail_generator = sparse_rail_generator(
            seed=self._config['seed'],
            max_num_cities=self._config['max_num_cities'],
            grid_mode=self._config['grid_mode'],
            max_rails_between_cities=self._config['max_rails_between_cities'],
            max_rails_in_city=self._config['max_rails_in_city']
        )

        return rail_generator

    def _launch(self):
        rail_generator = self.get_rail_generator()

        malfunction_generator = NoMalfunctionGen()
        if {'malfunction_rate', 'malfunction_min_duration', 'malfunction_max_duration'} <= self._config.keys():
            print("MALFUNCTIONS POSSIBLE")
            params = MalfunctionParameters(malfunction_rate=1 / self._config['malfunction_rate'],
                                           max_duration=self._config['malfunction_max_duration'],
                                           min_duration=self._config['malfunction_min_duration'])
            malfunction_generator = ParamMalfunctionGen(params)

        speed_ratio_map = None
        if 'speed_ratio_map' in self._config:
            speed_ratio_map = {
                float(k): float(v) for k, v in self._config['speed_ratio_map'].items()
            }
        if self._gym_env_class == SequentialFlatlandGymEnv:
            schedule_generator = SequentialSparseSchedGen(speed_ratio_map, seed=1)
        else:
            schedule_generator = sparse_schedule_generator(speed_ratio_map)

        env = None
        try:
            if self._fine_tune_env_path is None:
                env = RailEnv(
                    width=self._config['width'],
                    height=self._config['height'],
                    rail_generator=rail_generator,
                    schedule_generator=schedule_generator,
                    number_of_agents=self._config['number_of_agents'],
                    malfunction_generator=malfunction_generator,
                    obs_builder_object=self._observation.builder(),
                    remove_agents_at_target=True,
                    random_seed=self._config['seed'],
                    use_renderer=self._env_config.get('render')
                )
                env.reset()
            else:
                env, _ = RailEnvPersister.load_new(self._fine_tune_env_path)
                env.reset(regenerate_rail=False, regenerate_schedule=False)
                env.obs_builder = self._observation.builder()
                env.obs_builder.set_env(env)

        except ValueError as e:
            logging.error("=" * 50)
            logging.error(f"Error while creating env: {e}")
            logging.error("=" * 50)

        return env
