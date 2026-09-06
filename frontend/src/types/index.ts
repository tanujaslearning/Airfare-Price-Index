export interface HealthResponse {
  status: string;
  app: string;
  version: string;
  environment: string;
  database?: string;
}

export interface ApiResponse<T> {
  data: T;
  message?: string;
  timestamp?: string;
}

export type CollectionMode = 'LIVE' | 'MOCK';

export interface IndexLatestResponse {
  date: string;
  frequency: string;
  collection_mode: CollectionMode;
  index_value: number;
  baseline_period: string;
  ma_7d: number | null;
  ma_30d: number | null;
  dod_change_pct: number | null;
  calculated_at: string;
}

export interface AirfareIndexItem {
  id: number;
  date: string;
  frequency: string;
  collection_mode: CollectionMode;
  index_value: number;
  baseline_period: string;
  ma_7d: number | null;
  ma_30d: number | null;
  dod_change_pct: number | null;
  calculated_at: string;
}

export interface IndexHistoricalResponse {
  count: number;
  frequency: string;
  collection_mode: CollectionMode;
  start_date: string | null;
  end_date: string | null;
  items: AirfareIndexItem[];
}

export interface FilterOption {
  value: string;
  label: string;
  quote_count: number;
}

export interface FilterOptionsResponse {
  collection_mode: CollectionMode;
  origins: FilterOption[];
  destinations: FilterOption[];
  airlines: FilterOption[];
  periods: FilterOption[];
}

export interface RouteItem {
  id: number;
  route_code: string;
  route_key: string;
  origin: string;
  origin_code: string;
  destination: string;
  destination_code: string;
  distance: number | null;
  distance_km: number | null;
  passenger_market_weight: number | null;
  dgca_weight: number | null;
  is_active: boolean;
}

export type RouteWeightStatus = 'AVAILABLE' | 'MISSING' | 'NOT_MAPPED';

export interface RouteWeightItem {
  route_code: string;
  origin: string;
  destination: string;
  dgca_route_identifier: string | null;
  passenger_traffic: number | null;
  traffic_period: string | null;
  source: string;
  source_reference: string | null;
  directionality: 'directional' | 'combined city-pair' | null;
  status: RouteWeightStatus;
  weight: number | null;
}

export interface RouteWeightsResponse {
  source: string;
  traffic_period: string | null;
  directionality: string | null;
  routes: RouteWeightItem[];
  coverage: {
    available: number;
    total: number;
    percentage: number;
  };
  missing_routes: string[];
  unmapped_routes: string[];
  total_passenger_traffic: number;
}

export interface RouteWindowBreakdown {
  advance_window_days: number;
  window_label: string;
  mean_fare: number | null;
  baseline_fare: number | null;
  sub_index: number | null;
  quotes_count: number;
}

export interface RouteCorridorIndexResponse {
  route_code: string;
  route_key: string;
  origin: string | null;
  origin_code: string;
  destination: string | null;
  destination_code: string;
  distance: number | null;
  distance_km: number | null;
  passenger_market_weight: number | null;
  dgca_weight: number | null;
  collection_mode: CollectionMode;
  target_date: string;
  route_index: number | null;
  windows: RouteWindowBreakdown[];
  historical_points: Array<{ date: string; route_index: number | null }>;
}

export interface PipelineTriggerRequest {
  collection_date?: string | null;
  random_seed?: number | null;
  force_recalculate?: boolean;
}

export interface PipelineTriggerResponse {
  status: string;
  job_id: number;
  source: string;
  collection_date: string;
  ingested_count: number;
  processed_quotes_count: number;
  outliers_count: number;
  clean_usable_count: number;
  index_value: number | null;
  ma_7d: number | null;
  dod_change_pct: number | null;
  collection_mode: CollectionMode | null;
  timestamp: string;
}

export interface LiveIndexResponse {
  status: 'SUFFICIENT_COVERAGE' | 'INSUFFICIENT_COVERAGE';
  collection_mode: 'LIVE';
  collection_date: string | null;
  index_value: number | null;
  index_scope: string;
  coverage: {
    expected_route_window_combinations: number;
    observed_route_window_combinations: number;
    coverage_pct: number;
    minimum_required_coverage_pct: number;
    is_sufficient: boolean;
  };
  live_quote_count: number;
  routes_represented: number;
  advance_windows_represented: number;
  sources_represented: string[];
  route_values: LiveIndexRouteValue[];
}

export interface LiveIndexWindowValue {
  route: string;
  advance_window_days: number;
  quote_count: number;
  mean_fare: number;
  baseline_fare: number;
  sub_index: number;
  sources_used: string[];
}

export interface LiveIndexRouteValue {
  route: string;
  route_index: number;
  dgca_weight: number | null;
  quote_count: number;
  windows_observed: number;
  window_values: LiveIndexWindowValue[];
}

export interface LiveQuoteItem {
  quote_id: number;
  route: string;
  source: string;
  flight_number: string | null;
  departure_datetime: string;
  arrival_datetime: string | null;
  advance_window_days: number;
  base_fare: number;
  taxes_fees: number;
  total_fare: number;
  cabin_class: string;
  scraped_at: string;
  scraping_job_id: number | null;
}

export interface LiveQuotesResponse {
  total: number;
  limit: number;
  offset: number;
  data: LiveQuoteItem[];
}
