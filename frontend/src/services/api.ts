import axios from 'axios';
import {
  CollectionMode,
  HealthResponse,
  IndexLatestResponse,
  IndexHistoricalResponse,
  FilterOptionsResponse,
  LiveIndexResponse,
  LiveQuotesResponse,
  RouteItem,
  RouteWeightsResponse,
  RouteCorridorIndexResponse,
  PipelineTriggerRequest,
  PipelineTriggerResponse,
} from '../types';

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '',
  timeout: 30000, // 30s timeout to accommodate on-demand pipeline execution
  headers: {
    'Content-Type': 'application/json',
  },
});

/**
 * Health check endpoint.
 */
export const checkHealth = async (): Promise<HealthResponse> => {
  const response = await api.get<HealthResponse>('/api/health');
  return response.data;
};

/**
 * Retrieves the latest National Composite Airfare Price Index score.
 */
export const getLatestIndex = async (
  frequency: string = 'daily',
  collectionMode: CollectionMode = 'LIVE'
): Promise<IndexLatestResponse> => {
  const response = await api.get<IndexLatestResponse>('/api/v1/index/latest', {
    params: { frequency, collection_mode: collectionMode },
  });
  return response.data;
};

/**
 * Retrieves historical time-series index records with optional filters.
 */
export const getHistoricalIndex = async (params?: {
  start_date?: string;
  end_date?: string;
  frequency?: string;
  collection_mode?: CollectionMode;
  limit?: number;
}): Promise<IndexHistoricalResponse> => {
  const response = await api.get<IndexHistoricalResponse>('/api/v1/index/historical', {
    params: {
      frequency: params?.frequency || 'daily',
      collection_mode: params?.collection_mode || 'LIVE',
      limit: params?.limit || 100,
      start_date: params?.start_date,
      end_date: params?.end_date,
    },
  });
  return response.data;
};

/**
 * Retrieves read-only dashboard filter options derived from persisted data/configuration.
 */
export const getFilterOptions = async (
  collectionMode: CollectionMode = 'LIVE'
): Promise<FilterOptionsResponse> => {
  const response = await api.get<FilterOptionsResponse>('/api/v1/filters/options', {
    params: { collection_mode: collectionMode },
  });
  return response.data;
};

/**
 * Retrieves all monitored DGCA city-pair flight corridors.
 */
export const getRoutes = async (active_only: boolean = true): Promise<RouteItem[]> => {
  const response = await api.get<RouteItem[]>('/api/v1/routes', {
    params: { active_only },
  });
  return response.data;
};

/**
 * Retrieves official DGCA passenger-traffic weights for monitored routes.
 */
export const getRouteWeights = async (active_only: boolean = true): Promise<RouteWeightsResponse> => {
  const response = await api.get<RouteWeightsResponse>('/api/v1/routes/weights', {
    params: { active_only },
  });
  return response.data;
};

/**
 * Retrieves route-specific sub-index and advance purchase window breakdown (T+1 to T+45).
 */
export const getRouteIndex = async (
  routeCode: string,
  targetDate?: string,
  collectionMode: CollectionMode = 'LIVE',
  source?: string
): Promise<RouteCorridorIndexResponse> => {
  const response = await api.get<RouteCorridorIndexResponse>(
    `/api/v1/routes/${encodeURIComponent(routeCode)}/index`,
    {
      params: {
        ...(targetDate ? { target_date: targetDate } : {}),
        collection_mode: collectionMode,
        ...(source && source !== 'all' ? { source } : {}),
      },
    }
  );
  return response.data;
};

/**
 * Retrieves non-persisted live-only coverage and index analysis.
 */
export const getLiveIndex = async (params?: {
  collection_date?: string;
  route_code?: string;
  origin?: string;
  destination?: string;
  advance_window_days?: number;
  source?: string;
}): Promise<LiveIndexResponse> => {
  const response = await api.get<LiveIndexResponse>('/api/v1/index/live', {
    params: {
      collection_date: params?.collection_date,
      route_code: params?.route_code,
      origin: params?.origin,
      destination: params?.destination,
      advance_window_days: params?.advance_window_days,
      source: params?.source,
    },
  });
  return response.data;
};

/**
 * Retrieves persisted LIVE quote observations for inspection.
 */
export const getLiveQuotes = async (params?: {
  route?: string;
  source?: string;
  advance_window_days?: number;
  collection_date?: string;
  limit?: number;
  offset?: number;
}): Promise<LiveQuotesResponse> => {
  const response = await api.get<LiveQuotesResponse>('/api/v1/provenance/live-quotes', {
    params: {
      route: params?.route,
      source: params?.source,
      advance_window_days: params?.advance_window_days,
      collection_date: params?.collection_date,
      limit: params?.limit || 100,
      offset: params?.offset || 0,
    },
  });
  return response.data;
};

/**
 * Triggers the configured on-demand ingestion, cleaning, and index calculation pipeline.
 */
export const triggerPipeline = async (
  payload?: PipelineTriggerRequest
): Promise<PipelineTriggerResponse> => {
  const response = await api.post<PipelineTriggerResponse>(
    '/api/v1/pipeline/trigger',
    payload || {}
  );
  return response.data;
};

export default api;
