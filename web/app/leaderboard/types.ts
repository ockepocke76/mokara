export type CategoryOption = {
  key: string;
  label: string;
  description: string;
};

export type ProfileWeight = {
  key: string;
  name: string;
  description: string | null;
  weight: number;
};

export type Profile = {
  key: string;
  name: string;
  emoji: string | null;
  description: string | null;
  detailed_description: string | null;
  is_balanced: boolean;
  weights: ProfileWeight[];
};

export type EvaluationInfo = {
  settings_markdown: string;
  scenarios_markdown: string;
  score_components_markdown: string;
  wisdom_markdown: string;
};

export type LeaderboardMeta = {
  categories: CategoryOption[];
  default_category: string;
  profiles_by_category: Record<string, Profile[]>;
  evaluation_info: Record<string, EvaluationInfo>;
};

export type ScenarioResult = {
  name: string;
  sortino_ratio: number | null;
  success_rate: number | null;
};

export type Entry = {
  rank: number;
  id: number;
  strategy_name: string;
  badge: string;
  category: string | null;
  is_custom: boolean;
  author: string | null;
  score: number | null;
  description: string | null;
  metric_grid: { key: string; name: string; score: number; weight: number }[];
  scenario_results: ScenarioResult[];
  usage_clone_count: number;
  usage_fork_count: number;
  /** All-generations count: clones of clones, private ones included. */
  descendant_count: number;
  clone_target_id: number | null;
  in_library: boolean;
};

export type Board = {
  category: string;
  profile: string;
  profile_name: string;
  profile_is_balanced: boolean;
  total: number;
  entries: Entry[];
};
