import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  AlertCircle,
  BarChart3,
  CheckCircle2,
  Circle,
  Database,
  FileBarChart,
  Filter,
  Gauge,
  LayoutDashboard,
  LineChart as LineChartIcon,
  MapPin,
  Plane,
  RefreshCw,
  Route as RouteIcon,
  Settings,
} from 'lucide-react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import {
  checkHealth,
  getFilterOptions,
  getHistoricalIndex,
  getLatestIndex,
  getLiveIndex,
  getLiveQuotes,
  getRouteIndex,
  getRoutes,
  getRouteWeights,
  triggerPipeline,
} from '../services/api';
import {
  HealthResponse,
  IndexHistoricalResponse,
  IndexLatestResponse,
  FilterOptionsResponse,
  FilterOption,
  LiveIndexResponse,
  LiveQuoteItem,
  LiveQuotesResponse,
  PipelineTriggerResponse,
  RouteCorridorIndexResponse,
  RouteItem,
  RouteWindowBreakdown,
  RouteWeightItem,
  RouteWeightsResponse,
} from '../types';

type RouteSummary = {
  routeCode: string;
  avgFare: number;
  routeIndex: number | null;
  windowsObserved: number;
  quoteCount: number;
};

type AppliedFilters = {
  origin: string;
  destination: string;
  airline: string;
  period: string;
};

const navItems = [
  { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { id: 'trends', label: 'Airfare Trends', icon: LineChartIcon },
  { id: 'routes', label: 'Route Analysis', icon: RouteIcon },
  { id: 'airlines', label: 'Airline Analysis', icon: Plane },
  { id: 'cpi', label: 'CPI Insights', icon: Gauge },
  { id: 'explorer', label: 'Data Explorer', icon: Database },
  { id: 'reports', label: 'Reports', icon: FileBarChart },
  { id: 'settings', label: 'Settings', icon: Settings },
];

const DEFAULT_FILTERS: AppliedFilters = {
  origin: 'all',
  destination: 'all',
  airline: 'all',
  period: 'all',
};

const APPROVED_WINDOWS = [1, 7, 15, 30, 45];

const getErrorMessage = (err: unknown, fallback: string): string => {
  if (typeof err === 'object' && err !== null && 'response' in err) {
    const response = (err as {
      response?: {
        status?: number;
        data?: { detail?: string; message?: string };
      };
    }).response;

    if (response?.data?.detail) {
      return response.data.detail;
    }

    if (response?.data?.message) {
      return response.data.message;
    }

    if (response?.status) {
      return `${fallback} Status ${response.status}.`;
    }
  }

  return err instanceof Error ? err.message : fallback;
};

const EMPTY_VALUE = '—';

const formatNumber = (value: number | null | undefined, digits = 2): string => (
  value === null || value === undefined ? EMPTY_VALUE : value.toFixed(digits)
);

const formatFare = (value: number | null | undefined): string => (
  value === null || value === undefined
    ? EMPTY_VALUE
    : `INR ${Math.round(value).toLocaleString('en-IN')}`
);

const isNumber = (value: number | null | undefined): value is number => (
  value !== null && value !== undefined && Number.isFinite(value)
);

const isIndexDisplayable = (
  window: RouteWindowBreakdown
): window is RouteWindowBreakdown & { mean_fare: number; baseline_fare: number; sub_index: number } => (
  isNumber(window.mean_fare) && isNumber(window.baseline_fare) && isNumber(window.sub_index)
);

const formatDate = (value: string | null | undefined): string => {
  if (!value) {
    return EMPTY_VALUE;
  }

  return new Date(`${value}T00:00:00`).toLocaleDateString('en-IN', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  });
};

const getRouteAverageFare = (route: RouteCorridorIndexResponse | null): number | null => {
  if (!route || route.windows.length === 0) {
    return null;
  }

  const observedWindows = route.windows.filter((window) => window.quotes_count > 0);
  const windows = (observedWindows.length > 0 ? observedWindows : route.windows)
    .filter((window): window is RouteWindowBreakdown & { mean_fare: number } => isNumber(window.mean_fare));
  if (windows.length === 0) {
    return null;
  }
  return windows.reduce((sum, window) => sum + window.mean_fare, 0) / windows.length;
};

const isAll = (value: string): boolean => value === 'all';

const toRouteCode = (route: RouteItem): string => route.route_code || route.route_key;

const findRouteWeight = (
  routeWeights: RouteWeightsResponse | null,
  routeCode: string | null | undefined
): RouteWeightItem | null => (
  routeWeights?.routes.find((route) => route.route_code === routeCode) || null
);

const formatDgcaWeight = (routeWeight: RouteWeightItem | null): string => {
  if (!routeWeight) {
    return 'Not available';
  }
  if (routeWeight.status === 'NOT_MAPPED') {
    return 'Not mapped';
  }
  if (routeWeight.status === 'MISSING' || routeWeight.weight === null) {
    return 'Not available';
  }
  return `${(routeWeight.weight * 100).toFixed(1)}%`;
};

const filterRoutes = (routeList: RouteItem[], filters: AppliedFilters): RouteItem[] => (
  routeList.filter((route) => {
    const originMatch = isAll(filters.origin) || route.origin_code === filters.origin;
    const destinationMatch = isAll(filters.destination) || route.destination_code === filters.destination;
    return originMatch && destinationMatch;
  })
);

const routeCodeOptions = (routeList: RouteItem[], getCode: (route: RouteItem) => string): FilterOption[] => (
  Array.from(new Set(routeList.map(getCode)))
    .sort()
    .map((code) => ({ value: code, label: code, quote_count: 0 }))
);

const routeExists = (routeList: RouteItem[], origin: string, destination: string): boolean => (
  routeList.some((route) => {
    const originMatch = isAll(origin) || route.origin_code === origin;
    const destinationMatch = isAll(destination) || route.destination_code === destination;
    return originMatch && destinationMatch;
  })
);

const routeCoverageLabel = (route: RouteCorridorIndexResponse | null): string => {
  if (!route) {
    return 'No route selected';
  }
  const observed = route.windows.filter((window) => window.quotes_count > 0).length;
  return `Based on ${observed}/${route.windows.length} advance windows`;
};

const quoteCollectionDate = (quote: LiveQuoteItem): string => quote.scraped_at.slice(0, 10);

const quoteDepartureDate = (quote: LiveQuoteItem): string => quote.departure_datetime.slice(0, 10);

const pageIdFromHash = (): string => window.location.hash.replace(/^#\/?/, '') || 'dashboard';

const getLatestQuoteCollectionDate = (quotes: LiveQuoteItem[]): string | null => (
  quotes.reduce<string | null>((latest, quote) => {
    const collectionDate = quoteCollectionDate(quote);
    return !latest || collectionDate > latest ? collectionDate : latest;
  }, null)
);

const getCoverageByRoute = (quotes: LiveQuoteItem[], collectionDate: string | null): Map<string, Set<number>> => {
  const coverage = new Map<string, Set<number>>();

  quotes.forEach((quote) => {
    if (
      (collectionDate && quoteCollectionDate(quote) !== collectionDate)
      || !quote.route
      || !APPROVED_WINDOWS.includes(quote.advance_window_days)
      || quote.total_fare <= 0
    ) {
      return;
    }
    const coveredWindows = coverage.get(quote.route) || new Set<number>();
    coveredWindows.add(quote.advance_window_days);
    coverage.set(quote.route, coveredWindows);
  });

  return coverage;
};

export const HomePage: React.FC = () => {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [latestIndex, setLatestIndex] = useState<IndexLatestResponse | null>(null);
  const [historicalIndex, setHistoricalIndex] = useState<IndexHistoricalResponse | null>(null);
  const [liveIndex, setLiveIndex] = useState<LiveIndexResponse | null>(null);
  const [liveQuotes, setLiveQuotes] = useState<LiveQuotesResponse | null>(null);
  const [filterOptions, setFilterOptions] = useState<FilterOptionsResponse | null>(null);
  const [routes, setRoutes] = useState<RouteItem[]>([]);
  const [routeWeights, setRouteWeights] = useState<RouteWeightsResponse | null>(null);
  const [selectedRouteCode, setSelectedRouteCode] = useState<string>('');
  const [routeIndex, setRouteIndex] = useState<RouteCorridorIndexResponse | null>(null);
  const [routeSummaries, setRouteSummaries] = useState<RouteSummary[]>([]);

  const [draftOrigin, setDraftOrigin] = useState<string>('all');
  const [draftDestination, setDraftDestination] = useState<string>('all');
  const [draftAirline, setDraftAirline] = useState<string>('all');
  const [draftPeriod, setDraftPeriod] = useState<string>('all');
  const [appliedFilters, setAppliedFilters] = useState<AppliedFilters>(DEFAULT_FILTERS);
  const [activePage, setActivePage] = useState<string>(() => pageIdFromHash());

  const [loading, setLoading] = useState<boolean>(true);
  const [routeLoading, setRouteLoading] = useState<boolean>(false);
  const [summaryLoading, setSummaryLoading] = useState<boolean>(false);
  const [pipelineRunning, setPipelineRunning] = useState<boolean>(false);

  const [dashboardError, setDashboardError] = useState<string | null>(null);
  const [routeError, setRouteError] = useState<string | null>(null);
  const [pipelineError, setPipelineError] = useState<string | null>(null);
  const [pipelineResult, setPipelineResult] = useState<PipelineTriggerResponse | null>(null);

  const originOptions = useMemo(() => filterOptions?.origins || [], [filterOptions]);

  const destinationOptions = useMemo(() => filterOptions?.destinations || [], [filterOptions]);

  const routeOriginOptions = useMemo(() => {
    const scopedRoutes = isAll(draftDestination)
      ? routes
      : routes.filter((route) => route.destination_code === draftDestination);
    const options = routeCodeOptions(scopedRoutes, (route) => route.origin_code);
    return options.length > 0 ? options : originOptions;
  }, [draftDestination, originOptions, routes]);

  const routeDestinationOptions = useMemo(() => {
    const scopedRoutes = isAll(draftOrigin)
      ? routes
      : routes.filter((route) => route.origin_code === draftOrigin);
    const options = routeCodeOptions(scopedRoutes, (route) => route.destination_code);
    return options.length > 0 ? options : destinationOptions;
  }, [destinationOptions, draftOrigin, routes]);

  const airlineOptions = useMemo(() => filterOptions?.airlines || [], [filterOptions]);

  const periodOptions = useMemo(() => filterOptions?.periods || [], [filterOptions]);

  const filtersAreApplied = (
    !isAll(appliedFilters.origin)
    || !isAll(appliedFilters.destination)
    || !isAll(appliedFilters.airline)
    || !isAll(appliedFilters.period)
  );

  const availableRoutes = useMemo(() => filterRoutes(routes, appliedFilters), [appliedFilters, routes]);

  const availableRouteCodes = useMemo(
    () => new Set(availableRoutes.map((route) => toRouteCode(route))),
    [availableRoutes]
  );

  const filteredLiveQuotes = useMemo(() => (
    (liveQuotes?.data || []).filter((quote) => {
      const routeMatch = availableRouteCodes.size === 0
        ? !filtersAreApplied
        : availableRouteCodes.has(quote.route);
      const selectedAirline = airlineOptions.find((option) => option.value === appliedFilters.airline);
      const sourceMatch = isAll(appliedFilters.airline)
        || quote.source === appliedFilters.airline
        || quote.source === selectedAirline?.label;
      return routeMatch && sourceMatch;
    })
  ), [airlineOptions, appliedFilters.airline, availableRouteCodes, liveQuotes?.data, filtersAreApplied]);

  const latestObservationCollectionDate = useMemo(
    () => getLatestQuoteCollectionDate(filteredLiveQuotes),
    [filteredLiveQuotes]
  );

  const coverageByRoute = useMemo(
    () => getCoverageByRoute(filteredLiveQuotes, latestObservationCollectionDate),
    [filteredLiveQuotes, latestObservationCollectionDate]
  );

  const observedWindowCount = useMemo(() => (
    new Set((liveIndex?.route_values || []).flatMap((route) => (
      route.window_values.filter((window) => window.quote_count > 0).map((window) => window.advance_window_days)
    ))).size
  ), [liveIndex]);

  const sourceSummaries = useMemo(() => {
    const summaries = new Map<string, {
      source: string;
      quoteCount: number;
      routesCovered: Set<string>;
      windowsCovered: Set<number>;
      totalFare: number;
    }>();

    filteredLiveQuotes.forEach((quote) => {
      const current = summaries.get(quote.source) || {
        source: quote.source,
        quoteCount: 0,
        routesCovered: new Set<string>(),
        windowsCovered: new Set<number>(),
        totalFare: 0,
      };
      current.quoteCount += 1;
      current.routesCovered.add(quote.route);
      current.windowsCovered.add(quote.advance_window_days);
      current.totalFare += quote.total_fare;
      summaries.set(quote.source, current);
    });

    return Array.from(summaries.values())
      .map((summary) => ({
        source: summary.source,
        quoteCount: summary.quoteCount,
        routesCovered: summary.routesCovered.size,
        windowsCovered: summary.windowsCovered.size,
        avgFare: summary.quoteCount > 0 ? summary.totalFare / summary.quoteCount : null,
      }))
      .sort((a, b) => b.quoteCount - a.quoteCount);
  }, [filteredLiveQuotes]);

  const latestLiveQuotes = useMemo(() => (
    filteredLiveQuotes
      .slice()
      .sort((a, b) => b.scraped_at.localeCompare(a.scraped_at))
      .slice(0, 30)
  ), [filteredLiveQuotes]);

  const historicalChartData = useMemo(() => (
    (historicalIndex?.items || [])
      .filter((item) => isNumber(item.index_value))
      .map((item) => ({
        date: item.date.slice(5),
        fullDate: item.date,
        value: Number(item.index_value.toFixed(2)),
        ma7: isNumber(item.ma_7d) ? Number(item.ma_7d.toFixed(2)) : undefined,
      }))
  ), [historicalIndex]);

  const selectedRouteAverageFare = useMemo(() => getRouteAverageFare(routeIndex), [routeIndex]);

  const advanceWindowData = useMemo(() => (
    (routeIndex?.windows || []).map((window) => {
      const meanFare = window.quotes_count > 0 && isNumber(window.mean_fare)
        ? Math.round(window.mean_fare)
        : null;
      let baselineFare: number | null = null;
      let subIndex: number | null = null;

      if (window.quotes_count > 0 && isIndexDisplayable(window)) {
        baselineFare = Math.round(window.baseline_fare);
        subIndex = Number(window.sub_index.toFixed(1));
      }

      return {
        label: window.window_label || `T+${window.advance_window_days}`,
        meanFare,
        baselineFare,
        subIndex,
        quotes: window.quotes_count,
        hasData: meanFare !== null,
        hasIndexData: subIndex !== null,
      };
    })
  ), [routeIndex]);

  const observedAdvanceWindowData = useMemo(
    () => advanceWindowData.filter((window) => window.hasData),
    [advanceWindowData]
  );

  const routeBarData = useMemo(() => (
    routeSummaries
      .slice()
      .sort((a, b) => b.avgFare - a.avgFare)
      .map((route) => ({
        route: route.routeCode,
        avgFare: Math.round(route.avgFare),
        routeIndex: isNumber(route.routeIndex) ? route.routeIndex : null,
      }))
  ), [routeSummaries]);

  const cityRows = useMemo(() => {
    const cityMap = new Map<string, { code: string; origins: number; destinations: number }>();

    routes.forEach((route) => {
      const origin = cityMap.get(route.origin_code) || {
        code: route.origin_code,
        origins: 0,
        destinations: 0,
      };
      origin.origins += 1;
      cityMap.set(route.origin_code, origin);

      const destination = cityMap.get(route.destination_code) || {
        code: route.destination_code,
        origins: 0,
        destinations: 0,
      };
      destination.destinations += 1;
      cityMap.set(route.destination_code, destination);
    });

    return Array.from(cityMap.values()).sort(
      (a, b) => (b.origins + b.destinations) - (a.origins + a.destinations)
    );
  }, [routes]);

  const t1Window = routeIndex?.windows.find((window) => window.advance_window_days === 1);
  const t45Window = routeIndex?.windows.find((window) => window.advance_window_days === 45);

  const fetchRouteIndex = useCallback(async (routeCode: string, filters: AppliedFilters = appliedFilters) => {
    if (!routeCode) {
      setRouteIndex(null);
      setRouteError(null);
      return;
    }

    setRouteLoading(true);
    setRouteError(null);

    try {
      const data = await getRouteIndex(
        routeCode,
        undefined,
        'LIVE',
        isAll(filters.airline) ? undefined : filters.airline
      );
      setRouteIndex(data);
    } catch (err: unknown) {
      setRouteIndex(null);
      setRouteError(getErrorMessage(err, 'Unable to load route data.'));
    } finally {
      setRouteLoading(false);
    }
  }, [appliedFilters]);

  const fetchRouteSummaries = useCallback(async (routeList: RouteItem[], filters: AppliedFilters = appliedFilters) => {
    if (routeList.length === 0) {
      setRouteSummaries([]);
      return;
    }

    setSummaryLoading(true);

    try {
      const settled = await Promise.allSettled(
        routeList.map(async (route) => {
          const code = toRouteCode(route);
          const data = await getRouteIndex(
            code,
            undefined,
            'LIVE',
            isAll(filters.airline) ? undefined : filters.airline
          );
          const avgFare = getRouteAverageFare(data);

          return avgFare === null
            ? null
            : {
              routeCode: code,
              avgFare,
              routeIndex: data.route_index,
              windowsObserved: data.windows.filter((window) => window.quotes_count > 0).length,
              quoteCount: data.windows.reduce((sum, window) => sum + window.quotes_count, 0),
            };
        })
      );

      const summaries = settled
        .filter((item): item is PromiseFulfilledResult<RouteSummary | null> => item.status === 'fulfilled')
        .map((item) => item.value)
        .filter((item): item is RouteSummary => item !== null);

      setRouteSummaries(summaries);
    } finally {
      setSummaryLoading(false);
    }
  }, [appliedFilters]);

  const refreshDashboard = useCallback(async (
    filters: AppliedFilters = appliedFilters,
    preferredRouteCode?: string
  ) => {
    setLoading(true);
    setDashboardError(null);

    try {
      const [healthData, liveData, routesData, routeWeightData, filterData] = await Promise.all([
        checkHealth(),
        getLiveIndex({
          origin: isAll(filters.origin) ? undefined : filters.origin,
          destination: isAll(filters.destination) ? undefined : filters.destination,
          source: isAll(filters.airline) ? undefined : filters.airline,
        }),
        getRoutes(true),
        getRouteWeights(true),
        getFilterOptions('LIVE'),
      ]);
      const [latestResult, historicalResult, liveQuotesResult] = await Promise.allSettled([
        getLatestIndex('daily', 'LIVE'),
        getHistoricalIndex({
          frequency: 'daily',
          collection_mode: 'LIVE',
          limit: filters.period === 'all' ? 100 : Number(filters.period),
        }),
        getLiveQuotes({ limit: 500 }),
      ]);

      setHealth(healthData);
      setLiveIndex(liveData);
      setLatestIndex(latestResult.status === 'fulfilled' ? latestResult.value : null);
      setHistoricalIndex(historicalResult.status === 'fulfilled' ? historicalResult.value : null);
      setLiveQuotes(liveQuotesResult.status === 'fulfilled' ? liveQuotesResult.value : null);
      setRoutes(routesData);
      setRouteWeights(routeWeightData);
      setFilterOptions(filterData);

      if (liveData.status === 'INSUFFICIENT_COVERAGE') {
        setDashboardError(
          `LIVE DATA: Insufficient live coverage (${liveData.coverage.observed_route_window_combinations} / ${liveData.coverage.expected_route_window_combinations} route-window combinations).`
        );
      } else if (latestResult.status === 'rejected') {
        setDashboardError(getErrorMessage(latestResult.reason, 'Unable to load latest LIVE index.'));
      } else if (historicalResult.status === 'rejected') {
        setDashboardError(getErrorMessage(historicalResult.reason, 'Unable to load historical LIVE index.'));
      }

      const scopedRoutes = filterRoutes(routesData, filters);
      const requestedCode = preferredRouteCode || selectedRouteCode;
      const routeStillAvailable = scopedRoutes.some(
        (route) => toRouteCode(route) === requestedCode || route.route_key === requestedCode
      );
      const nextRouteCode = routeStillAvailable
        ? requestedCode
        : scopedRoutes[0] ? toRouteCode(scopedRoutes[0]) : '';

      setSelectedRouteCode(nextRouteCode);

      await Promise.all([
        nextRouteCode ? fetchRouteIndex(nextRouteCode, filters) : Promise.resolve(setRouteIndex(null)),
        fetchRouteSummaries(scopedRoutes, filters),
      ]);
    } catch (err: unknown) {
      setDashboardError(getErrorMessage(err, 'Unable to refresh dashboard data.'));
    } finally {
      setLoading(false);
    }
  }, [appliedFilters, fetchRouteIndex, fetchRouteSummaries, selectedRouteCode]);

  const applyFilters = () => {
    const nextFilters = {
      origin: draftOrigin,
      destination: draftDestination,
      airline: draftAirline,
      period: draftPeriod,
    };
    setAppliedFilters(nextFilters);

    const matchingRoute = filterRoutes(routes, nextFilters)[0];
    const nextRouteCode = matchingRoute ? toRouteCode(matchingRoute) : '';

    setSelectedRouteCode(nextRouteCode);
    refreshDashboard(nextFilters, nextRouteCode);
  };

  const changeDraftOrigin = (value: string) => {
    setDraftOrigin(value);
    if (!isAll(draftDestination) && !routeExists(routes, value, draftDestination)) {
      setDraftDestination(DEFAULT_FILTERS.destination);
    }
  };

  const changeDraftDestination = (value: string) => {
    setDraftDestination(value);
    if (!isAll(draftOrigin) && !routeExists(routes, draftOrigin, value)) {
      setDraftOrigin(DEFAULT_FILTERS.origin);
    }
  };

  const resetFilters = () => {
    setDraftOrigin(DEFAULT_FILTERS.origin);
    setDraftDestination(DEFAULT_FILTERS.destination);
    setDraftAirline(DEFAULT_FILTERS.airline);
    setDraftPeriod(DEFAULT_FILTERS.period);
    setAppliedFilters(DEFAULT_FILTERS);
    refreshDashboard(DEFAULT_FILTERS);
  };

  const runPipeline = async () => {
    setPipelineRunning(true);
    setPipelineError(null);

    try {
      const result = await triggerPipeline({ random_seed: 42, force_recalculate: true });
      setPipelineResult(result);
      await refreshDashboard(appliedFilters, selectedRouteCode);
    } catch (err: unknown) {
      setPipelineError(getErrorMessage(err, 'Pipeline failed.'));
    } finally {
      setPipelineRunning(false);
    }
  };

  useEffect(() => {
    refreshDashboard();
  }, []);

  useEffect(() => {
    if (selectedRouteCode) {
      fetchRouteIndex(selectedRouteCode, appliedFilters);
    }
  }, [appliedFilters, fetchRouteIndex, selectedRouteCode]);

  useEffect(() => {
    const onHashChange = () => {
      setActivePage(pageIdFromHash());
    };
    window.addEventListener('hashchange', onHashChange);
    return () => window.removeEventListener('hashchange', onHashChange);
  }, []);

  const navigateTo = (pageId: string) => {
    window.location.hash = pageId === 'dashboard' ? '' : pageId;
    setActivePage(pageId);
  };

  const liveIndexValue = liveIndex?.index_value ?? (filtersAreApplied ? null : latestIndex?.index_value) ?? null;
  const liveCoverage = liveIndex?.coverage;
  const liveIndexSublabel = liveIndex?.index_value !== null && liveIndex?.index_value !== undefined
    ? `${liveIndex.index_scope.toLowerCase()} live scope`
    : liveCoverage
      ? `Insufficient LIVE coverage (${liveCoverage.observed_route_window_combinations}/${liveCoverage.expected_route_window_combinations} route-window cells)`
      : 'Insufficient LIVE coverage';
  const liveIndexDisplayValue = loading
    ? 'Loading'
    : liveIndexValue === null
      ? 'APIx unavailable'
      : formatNumber(liveIndexValue);
  const latestCollectionDate = liveIndex?.collection_date ?? latestIndex?.date ?? null;
  const selectedRouteWeight = findRouteWeight(routeWeights, routeIndex?.route_code);
  const routeFilterEmpty = filtersAreApplied && availableRoutes.length === 0;
  const routeFilterEmptyLabel = 'No prescribed route matches the selected filters.';
  const routeFilterEmptyHint = 'Select a route from the configured DGCA-based route basket.';

  const insights = [
    `Current LIVE scope index is ${formatNumber(liveIndexValue)}.`,
    liveIndex?.status === 'INSUFFICIENT_COVERAGE'
      ? `LIVE DATA: Insufficient live coverage (${liveIndex.coverage.observed_route_window_combinations} / ${liveIndex.coverage.expected_route_window_combinations} route-window combinations).`
      : null,
    routeFilterEmpty
      ? routeFilterEmptyLabel
      : `${availableRoutes.length} prescribed routes match the applied route filters.`,
    routeIndex ? `Selected route ${routeIndex.route_code} has sub-index ${formatNumber(routeIndex.route_index)}. ${routeCoverageLabel(routeIndex)}.` : null,
    t1Window && t45Window && t1Window.quotes_count > 0 && t45Window.quotes_count > 0 && isNumber(t1Window.mean_fare) && isNumber(t45Window.mean_fare)
      ? `T+1 fare is ${t1Window.mean_fare >= t45Window.mean_fare ? 'higher' : 'lower'} than T+45.`
      : null,
  ].filter((item): item is string => Boolean(item));

  return (
    <div className="min-h-screen bg-slate-100 text-slate-900 lg:flex">
      <aside className="bg-slate-950 text-slate-100 lg:fixed lg:inset-y-0 lg:left-0 lg:w-64">
        <div className="flex h-full flex-col px-4 py-5">
          <div className="mb-7 flex items-center gap-3 px-2">
            <div className="flex h-9 w-9 items-center justify-center rounded-md bg-sky-500 text-white">
              <Plane className="h-5 w-5 -rotate-45" />
            </div>
            <div>
              <div className="text-sm font-bold uppercase tracking-wide">Airfare Index</div>
              <div className="text-[11px] text-slate-400">India Airfare Price Index</div>
            </div>
          </div>

          <nav className="space-y-1">
            {navItems.map(({ id, label, icon: Icon }) => (
              <button
                key={label}
                type="button"
                onClick={() => navigateTo(id)}
                className={`flex items-center gap-3 rounded-md px-3 py-2 text-sm ${
                  activePage === id
                    ? 'bg-sky-500 text-white shadow-sm'
                    : 'text-slate-300 hover:bg-slate-900 hover:text-white'
                } w-full text-left`}
              >
                <Icon className="h-4 w-4" />
                <span>{label}</span>
              </button>
            ))}
          </nav>

          <div className="mt-auto rounded-md border border-slate-800 bg-slate-900 px-3 py-3">
            <div className="flex items-center gap-2 text-xs font-semibold">
              <span className="h-2 w-2 rounded-full bg-emerald-400" />
              Live Data
            </div>
            <div className="mt-1 text-[11px] text-slate-400">
              {health?.status === 'healthy' ? 'API online' : 'Checking service'}
            </div>
          </div>
        </div>
      </aside>

      <main className="min-w-0 flex-1 lg:ml-64">
        <div className="mx-auto max-w-[1500px] px-4 py-4 sm:px-5 lg:px-6">
          <header className="mb-4 rounded-md border border-slate-200 bg-white px-4 py-3 shadow-sm">
            <div className="flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
              <div>
                <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wide text-sky-700">
                  <span className="h-2 w-2 rounded-full bg-emerald-500" />
                  Live Data
                </div>
                <h1 className="mt-1 text-xl font-bold tracking-normal text-slate-950">
                  INDIA AIRFARE PRICE INDEX
                </h1>
                <p className="mt-0.5 text-sm text-slate-500">
                  Daily Airfare Monitoring & CPI Augmentation
                </p>
              </div>

              <div className="flex flex-wrap items-end gap-2">
                <FilterSelect label="Origin" value={draftOrigin} onChange={changeDraftOrigin} options={routeOriginOptions} />
                <FilterSelect label="Destination" value={draftDestination} onChange={changeDraftDestination} options={routeDestinationOptions} />
                <FilterSelect
                  label="Airline"
                  value={draftAirline}
                  onChange={setDraftAirline}
                  options={airlineOptions}
                  emptyLabel="No live airline data"
                />

                <label className="text-[11px] font-medium text-slate-500">
                  Period
                  <select
                    value={draftPeriod}
                    onChange={(event) => setDraftPeriod(event.target.value)}
                    className="mt-1 block h-8 min-w-28 rounded-md border border-slate-200 bg-white px-2 text-xs text-slate-800 outline-none focus:border-sky-500"
                  >
                    {(periodOptions.length > 0 ? periodOptions : [
                      { value: 'all', label: 'All', quote_count: 0 },
                      { value: '7', label: 'Last 7', quote_count: 0 },
                      { value: '30', label: 'Last 30', quote_count: 0 },
                    ]).map((option) => (
                      <option key={option.value} value={option.value}>{option.label}</option>
                    ))}
                  </select>
                </label>

                <button
                  type="button"
                  onClick={applyFilters}
                  disabled={loading}
                  className="inline-flex h-8 items-center gap-2 rounded-md bg-sky-600 px-3 text-xs font-semibold text-white shadow-sm hover:bg-sky-700 disabled:opacity-50"
                >
                  <Filter className="h-3.5 w-3.5" />
                  {loading ? 'Applying' : 'Apply'}
                </button>

                <button
                  type="button"
                  onClick={resetFilters}
                  disabled={loading}
                  className="inline-flex h-8 items-center rounded-md border border-slate-200 bg-white px-3 text-xs font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50"
                >
                  Reset
                </button>

                <button
                  type="button"
                  onClick={runPipeline}
                  disabled={pipelineRunning}
                  className="inline-flex h-8 items-center gap-2 rounded-md border border-slate-200 bg-white px-3 text-xs font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50"
                >
                  <RefreshCw className={`h-3.5 w-3.5 ${pipelineRunning ? 'animate-spin' : ''}`} />
                  {pipelineRunning ? 'Running' : 'Run Pipeline'}
                </button>
              </div>
            </div>

            {(dashboardError || pipelineError || pipelineResult) && (
              <div className="mt-3 rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-600">
                {dashboardError && (
                  <StatusLine tone="error" label={dashboardError} />
                )}
                {pipelineError && (
                  <StatusLine tone="error" label={pipelineError} />
                )}
                {pipelineResult && !pipelineError && (
                  <details>
                    <summary className="cursor-pointer text-slate-700">
                      Pipeline completed. Index {formatNumber(pipelineResult.index_value)} from {pipelineResult.clean_usable_count} usable quotes.
                    </summary>
                    <div className="mt-2 grid gap-2 text-slate-500 sm:grid-cols-3">
                      <span>Job #{pipelineResult.job_id}</span>
                      <span>Ingested {pipelineResult.ingested_count}</span>
                      <span>Outliers {pipelineResult.outliers_count}</span>
                    </div>
                  </details>
                )}
              </div>
            )}
          </header>

          {activePage === 'dashboard' ? (
            <>
          <section className="mb-4 grid grid-cols-2 gap-3 lg:grid-cols-5">
            <KpiCard
              label="Airfare Price Index"
              value={liveIndexDisplayValue}
              sublabel={liveIndexSublabel}
              tone="blue"
            />
            <KpiCard
              label="Average Airfare"
              value={formatFare(selectedRouteAverageFare)}
              sublabel={routeIndex ? routeIndex.route_code : 'Selected route'}
              tone="green"
            />
            <KpiCard
              label="Routes Tracked"
              value={loading ? 'Loading' : String(availableRoutes.length)}
              sublabel={routeFilterEmpty ? 'No prescribed route match' : filtersAreApplied ? 'Matching route filters' : 'Active DGCA corridors'}
              tone="slate"
            />
            <KpiCard
              label="Advance Windows"
              value={routeIndex ? `${routeIndex.windows.filter((window) => window.quotes_count > 0).length}/${routeIndex.windows.length}` : EMPTY_VALUE}
              sublabel="Observed LIVE windows"
              tone="indigo"
            />
            <KpiCard
              label="Last Updated"
              value={latestCollectionDate ? formatDate(latestCollectionDate) : 'No LIVE collection'}
              sublabel={latestCollectionDate ? 'Latest LIVE collection date' : 'No LIVE collection'}
              tone="amber"
            />
          </section>

          <section className="grid grid-cols-1 gap-4 xl:grid-cols-12">
            <DashboardCard className="xl:col-span-7" title="AIRFARE PRICE INDEX TREND">
              {loading || !historicalIndex ? (
                <LoadingState label="Loading index trend..." />
              ) : historicalChartData.length === 0 ? (
                <EmptyState
                  label="No historical APIx data available yet."
                  sublabel="Daily historical APIx will appear after sufficient LIVE coverage is collected."
                />
              ) : historicalChartData.length === 1 ? (
                <SingleObservation
                  value={historicalChartData[0].value}
                  date={historicalChartData[0].fullDate}
                />
              ) : (
                <div className="h-52">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={historicalChartData} margin={{ top: 8, right: 18, bottom: 2, left: -16 }}>
                      <CartesianGrid stroke="#eef2f7" vertical={false} />
                      <XAxis dataKey="date" tick={{ fontSize: 11, fill: '#64748b' }} tickLine={false} axisLine={false} />
                      <YAxis tick={{ fontSize: 11, fill: '#64748b' }} tickLine={false} axisLine={false} domain={['dataMin - 5', 'dataMax + 5']} />
                      <Tooltip
                        contentStyle={{ border: '1px solid #e2e8f0', borderRadius: 6, fontSize: 12 }}
                        formatter={(value: number) => [value.toFixed(2), 'Index']}
                        labelFormatter={(_, payload) => payload?.[0]?.payload?.fullDate || ''}
                      />
                      <Line type="monotone" dataKey="value" stroke="#2563eb" strokeWidth={2.5} dot={{ r: 3 }} activeDot={{ r: 5 }} />
                      <Line type="monotone" dataKey="ma7" stroke="#0f766e" strokeWidth={1.5} dot={false} strokeDasharray="4 3" />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              )}
            </DashboardCard>

            <DashboardCard className="xl:col-span-5" title="ROUTE-WISE AVERAGE FARE (INR)">
              {summaryLoading ? (
                <LoadingState label="Loading route fares..." />
              ) : routeBarData.length === 0 ? (
                <EmptyState label="Route fare data is not available yet." />
              ) : (
                <div className="h-52">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={routeBarData} layout="vertical" margin={{ top: 4, right: 22, left: 16, bottom: 0 }}>
                      <CartesianGrid stroke="#eef2f7" horizontal={false} />
                      <XAxis type="number" hide />
                      <YAxis dataKey="route" type="category" width={62} tick={{ fontSize: 11, fill: '#334155' }} axisLine={false} tickLine={false} />
                      <Tooltip
                        cursor={{ fill: '#f8fafc' }}
                        contentStyle={{ border: '1px solid #e2e8f0', borderRadius: 6, fontSize: 12 }}
                        formatter={(value: number) => [formatFare(value), 'Average fare']}
                      />
                      <Bar dataKey="avgFare" radius={[0, 4, 4, 0]} barSize={14}>
                        {routeBarData.map((entry) => (
                          <Cell key={entry.route} fill={entry.route === selectedRouteCode ? '#2563eb' : '#60a5fa'} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}
            </DashboardCard>

            <DashboardCard className="xl:col-span-5" title="ADVANCE BOOKING WINDOW ANALYSIS">
              {routeLoading ? (
                <LoadingState label="Loading booking windows..." />
              ) : routeIndex ? (
                <div className="space-y-3">
                  {observedAdvanceWindowData.length === 0 ? (
                    <EmptyState label="No live index data available for this route/window." />
                  ) : (
                    <div className="h-28">
                      <ResponsiveContainer width="100%" height="100%">
                        <BarChart data={observedAdvanceWindowData} margin={{ top: 4, right: 6, bottom: 0, left: -24 }}>
                          <CartesianGrid stroke="#eef2f7" vertical={false} />
                          <XAxis dataKey="label" tick={{ fontSize: 11, fill: '#334155' }} tickLine={false} axisLine={false} />
                          <YAxis tick={{ fontSize: 10, fill: '#64748b' }} tickLine={false} axisLine={false} />
                          <Tooltip
                            cursor={{ fill: '#f8fafc' }}
                            contentStyle={{ border: '1px solid #e2e8f0', borderRadius: 6, fontSize: 12 }}
                            formatter={(value) => [typeof value === 'number' ? formatFare(value) : EMPTY_VALUE, 'Mean fare']}
                          />
                          <Bar dataKey="meanFare" fill="#2563eb" radius={[4, 4, 0, 0]} barSize={22} />
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  )}

                  <CompactWindowTable windows={advanceWindowData} />
                </div>
              ) : (
                <EmptyState
                  label={routeFilterEmpty ? routeFilterEmptyLabel : 'No route selected.'}
                  sublabel={routeFilterEmpty ? routeFilterEmptyHint : undefined}
                />
              )}
            </DashboardCard>

            <DashboardCard className="xl:col-span-7" title="ROUTE ANALYSIS">
              <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                <select
                  value={selectedRouteCode}
                  onChange={(event) => setSelectedRouteCode(event.target.value)}
                  className="h-8 rounded-md border border-slate-200 bg-white px-2 text-xs font-medium text-slate-800 outline-none focus:border-sky-500"
                >
                  {availableRoutes.length === 0 ? (
                    <option value="">No matching routes</option>
                  ) : (
                    availableRoutes.map((route) => (
                      <option key={route.id} value={route.route_code || route.route_key}>
                        {route.route_code} ({route.origin_code}-{route.destination_code})
                      </option>
                    ))
                  )}
                </select>
                <button
                  type="button"
                  onClick={() => fetchRouteIndex(selectedRouteCode)}
                  disabled={routeLoading || !selectedRouteCode}
                  className="inline-flex h-8 items-center gap-2 rounded-md border border-slate-200 px-3 text-xs font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50"
                >
                  <RefreshCw className={`h-3.5 w-3.5 ${routeLoading ? 'animate-spin' : ''}`} />
                  Refresh
                </button>
              </div>

              {routeLoading ? (
                <LoadingState label="Loading route data..." />
              ) : routeError ? (
                <EmptyState label={routeError} />
              ) : routeIndex ? (
                <div className="space-y-3">
                  <div className="grid gap-3 sm:grid-cols-4">
                    <Metric label="Selected route" value={routeIndex.route_code} />
                    <Metric label="Distance" value={routeIndex.distance ? `${routeIndex.distance.toLocaleString()} km` : EMPTY_VALUE} />
                    <Metric
                      label="DGCA weight"
                      value={formatDgcaWeight(selectedRouteWeight)}
                      sublabel={selectedRouteWeight?.traffic_period || undefined}
                    />
                    <Metric label="LIVE Route Sub-Index" value={formatNumber(routeIndex.route_index)} sublabel={routeCoverageLabel(routeIndex)} />
                  </div>

                  <div className="space-y-2">
                    {routeIndex.windows.map((window) => (
                      (() => {
                        const subIndex = window.quotes_count > 0 && isIndexDisplayable(window)
                          ? window.sub_index
                          : null;
                        const hasIndexData = subIndex !== null;
                        return (
                          <div key={window.advance_window_days} className="grid grid-cols-[42px_1fr_52px] items-center gap-3 text-xs">
                            <div className="font-semibold text-slate-800">{window.window_label}</div>
                            <div className="h-2 rounded-full bg-slate-100">
                              <div
                                className={`h-2 rounded-full ${hasIndexData ? 'bg-sky-500' : 'bg-transparent'}`}
                                style={{ width: hasIndexData ? `${Math.min(100, Math.max(8, subIndex))}%` : '0%' }}
                              />
                            </div>
                            <div className={`text-right font-semibold ${hasIndexData ? 'text-sky-700' : 'text-slate-400'}`}>
                              {hasIndexData ? formatNumber(subIndex, 1) : EMPTY_VALUE}
                            </div>
                          </div>
                        );
                      })()
                    ))}
                  </div>
                </div>
              ) : (
                <EmptyState label="No route selected." />
              )}
            </DashboardCard>

            <DashboardCard className="xl:col-span-6" title="CITY / REGION ANALYSIS">
              <div className="grid gap-2 sm:grid-cols-2">
                {cityRows.map((city) => (
                  <div key={city.code} className="flex items-center justify-between rounded-md border border-slate-100 bg-slate-50 px-3 py-2">
                    <div className="flex items-center gap-2">
                      <MapPin className="h-3.5 w-3.5 text-sky-600" />
                      <span className="text-sm font-semibold text-slate-800">{city.code}</span>
                    </div>
                    <span className="text-xs text-slate-500">
                      {city.origins} origin / {city.destinations} destination
                    </span>
                  </div>
                ))}
              </div>
            </DashboardCard>

            <DashboardCard className="xl:col-span-6" title="KEY INSIGHTS">
              <div className="grid gap-2 sm:grid-cols-2">
                {insights.map((insight) => (
                  <div key={insight} className="flex gap-2 text-sm text-slate-700">
                    <CheckCircle2 className="mt-0.5 h-4 w-4 flex-shrink-0 text-sky-600" />
                    <span>{insight}</span>
                  </div>
                ))}
              </div>
            </DashboardCard>
          </section>
            </>
          ) : (
            <SectionPage
              pageId={activePage}
              historicalChartData={historicalChartData}
              routeIndex={routeIndex}
              routeSummaries={routeSummaries}
              liveIndex={liveIndex}
              liveQuotes={latestLiveQuotes}
              sourceSummaries={sourceSummaries}
              coverageByRoute={coverageByRoute}
              observedWindowCount={observedWindowCount}
              latestCollectionDate={latestCollectionDate}
              health={health}
              routes={availableRoutes}
              routeWeights={routeWeights}
              loading={loading || routeLoading || summaryLoading}
              filtersAreApplied={filtersAreApplied}
            />
          )}
        </div>
      </main>
    </div>
  );
};

interface SectionPageProps {
  pageId: string;
  historicalChartData: Array<{ date: string; fullDate: string; value: number; ma7?: number }>;
  routeIndex: RouteCorridorIndexResponse | null;
  routeSummaries: RouteSummary[];
  liveIndex: LiveIndexResponse | null;
  liveQuotes: LiveQuoteItem[];
  sourceSummaries: Array<{
    source: string;
    quoteCount: number;
    routesCovered: number;
    windowsCovered: number;
    avgFare: number | null;
  }>;
  coverageByRoute: Map<string, Set<number>>;
  observedWindowCount: number;
  latestCollectionDate: string | null;
  health: HealthResponse | null;
  routes: RouteItem[];
  routeWeights: RouteWeightsResponse | null;
  loading: boolean;
  filtersAreApplied: boolean;
}

const sectionTitles: Record<string, string> = {
  trends: 'Airfare Trends',
  routes: 'Route Analysis',
  airlines: 'Airline Analysis',
  cpi: 'CPI Insights',
  explorer: 'Data Explorer',
  reports: 'Reports',
  settings: 'Settings',
};

const SectionPage: React.FC<SectionPageProps> = ({
  pageId,
  historicalChartData,
  routeIndex,
  routeSummaries,
  liveIndex,
  liveQuotes,
  sourceSummaries,
  coverageByRoute,
  observedWindowCount,
  latestCollectionDate,
  health,
  routes,
  routeWeights,
  loading,
  filtersAreApplied,
}) => {
  const title = sectionTitles[pageId] || 'Dashboard';

  if (loading) {
    return <LoadingState label={`Loading ${title.toLowerCase()}...`} />;
  }

  if (pageId === 'trends') {
    const latestPoint = historicalChartData[historicalChartData.length - 1];
    const previousPoint = historicalChartData.length > 1 ? historicalChartData[historicalChartData.length - 2] : null;
    const changePct = latestPoint && previousPoint
      ? ((latestPoint.value - previousPoint.value) / previousPoint.value) * 100
      : null;

    return (
      <div className="grid gap-4 xl:grid-cols-12">
        <DashboardCard className="xl:col-span-8" title="AIRFARE TRENDS">
          {historicalChartData.length === 0 ? (
            <div className="space-y-3">
              <EmptyState
                label="No historical APIx data available yet."
                sublabel="Daily historical APIx will appear after sufficient LIVE coverage is collected."
              />
              <div className="grid gap-3 sm:grid-cols-4">
                <Metric label="Routes" value={String(routes.length)} />
                <Metric label="Booking windows" value={String(APPROVED_WINDOWS.length)} />
                <Metric
                  label="LIVE cells"
                  value={`${liveIndex?.coverage.observed_route_window_combinations || 0}/${liveIndex?.coverage.expected_route_window_combinations || routes.length * APPROVED_WINDOWS.length}`}
                  sublabel="Route-window coverage"
                />
                <Metric label="Observed windows" value={`${observedWindowCount}/${APPROVED_WINDOWS.length}`} />
              </div>
            </div>
          ) : (
            <div className="space-y-3">
              <div className="grid gap-3 sm:grid-cols-3">
                <Metric label="Latest available APIx" value={formatNumber(latestPoint?.value)} sublabel={latestPoint?.fullDate} />
                <Metric label="Previous APIx" value={formatNumber(previousPoint?.value)} sublabel={previousPoint?.fullDate || 'Need another observation'} />
                <Metric label="Change" value={changePct === null ? EMPTY_VALUE : `${changePct.toFixed(2)}%`} sublabel="Daily change" />
              </div>
              <div className="h-72">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={historicalChartData} margin={{ top: 8, right: 18, bottom: 2, left: -16 }}>
                    <CartesianGrid stroke="#eef2f7" vertical={false} />
                    <XAxis dataKey="date" tick={{ fontSize: 11, fill: '#64748b' }} tickLine={false} axisLine={false} />
                    <YAxis tick={{ fontSize: 11, fill: '#64748b' }} tickLine={false} axisLine={false} domain={['dataMin - 5', 'dataMax + 5']} />
                    <Tooltip contentStyle={{ border: '1px solid #e2e8f0', borderRadius: 6, fontSize: 12 }} />
                    <Line type="monotone" dataKey="value" stroke="#2563eb" strokeWidth={2.5} dot={{ r: 3 }} />
                    <Line type="monotone" dataKey="ma7" stroke="#0f766e" strokeWidth={1.5} dot={false} strokeDasharray="4 3" />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}
        </DashboardCard>
        <DashboardCard className="xl:col-span-4" title="TREND FILTER SUPPORT">
          <div className="grid gap-3">
            <Metric label="Route filter" value="Global route filters" sublabel={`${routes.length} prescribed routes in scope`} />
            <Metric label="Booking-window filter" value="Coverage only" sublabel="National APIx history is all-window" />
            <Metric label="Collection date axis" value="Daily" sublabel="X-axis uses collection date" />
          </div>
        </DashboardCard>
      </div>
    );
  }

  if (pageId === 'routes') {
    return (
      <div className="grid gap-4 xl:grid-cols-2">
        <DashboardCard title="ROUTE ANALYSIS">
          {routeIndex ? (
            <div className="space-y-4">
              <div className="grid gap-3 sm:grid-cols-3">
                <Metric label="Route" value={routeIndex.route_code} />
                <Metric label="Origin" value={routeIndex.origin_code || EMPTY_VALUE} />
                <Metric label="Destination" value={routeIndex.destination_code || EMPTY_VALUE} />
                <Metric
                  label="DGCA weight"
                  value={formatDgcaWeight(findRouteWeight(routeWeights, routeIndex.route_code))}
                  sublabel={findRouteWeight(routeWeights, routeIndex.route_code)?.traffic_period || undefined}
                />
                <Metric label="LIVE Route Sub-Index" value={formatNumber(routeIndex.route_index)} sublabel={routeCoverageLabel(routeIndex)} />
                <Metric label="LIVE quotes" value={String(routeIndex.windows.reduce((sum, window) => sum + window.quotes_count, 0))} />
              </div>
              <BookingWindowTable windows={routeIndex.windows} />
            </div>
          ) : (
            <EmptyState
              label={filtersAreApplied ? 'No prescribed route matches the selected filters.' : 'No route selected.'}
              sublabel={filtersAreApplied ? 'Select a route from the configured DGCA-based route basket.' : undefined}
            />
          )}
        </DashboardCard>
        <DashboardCard title="ROUTE FARE COMPARISON">
          {routes.length === 0 ? (
            <EmptyState
              label="No prescribed route matches the selected filters."
              sublabel="Select a route from the configured DGCA-based route basket."
            />
          ) : (
            <>
              <RouteComparisonTable routes={routes} routeSummaries={routeSummaries} />
              <div className="hidden">
              {routeSummaries.map((route) => (
                <div key={route.routeCode} className="flex items-center justify-between rounded-md bg-slate-50 px-3 py-2 text-sm">
                  <span className="font-semibold text-slate-800">{route.routeCode}</span>
                  <span className="text-slate-500">{formatFare(route.avgFare)} · {route.windowsObserved}/5 windows · {route.quoteCount} quotes</span>
                </div>
              ))}
              </div>
            </>
          )}
        </DashboardCard>
      </div>
    );
  }

  if (pageId === 'airlines') {
    return (
      <div className="grid gap-4 xl:grid-cols-3">
        <DashboardCard className="xl:col-span-2" title="AIRLINE ANALYSIS">
          {sourceSummaries.length > 0 ? (
            <div className="space-y-2">
              {sourceSummaries.map((source) => (
                <div key={source.source} className="grid gap-2 rounded-md bg-slate-50 px-3 py-3 text-sm sm:grid-cols-5">
                  <div className="font-semibold text-slate-900">{source.source}</div>
                  <div><span className="text-slate-500">LIVE observations</span><div className="font-semibold">{source.quoteCount}</div></div>
                  <div><span className="text-slate-500">Routes covered</span><div className="font-semibold">{source.routesCovered}</div></div>
                  <div><span className="text-slate-500">Windows covered</span><div className="font-semibold">{source.windowsCovered}</div></div>
                  <div><span className="text-slate-500">Avg fare</span><div className="font-semibold">{formatFare(source.avgFare)}</div></div>
                </div>
              ))}
            </div>
          ) : (
            <EmptyState label="No persisted LIVE observations match these filters." />
          )}
        </DashboardCard>
        <DashboardCard title="SOURCE DISPLAY RULE">
          <div className="space-y-3 text-sm text-slate-600">
            <p>Only sources with persisted LIVE observations are shown.</p>
            <p>Sources without validated LIVE rows are not represented as successfully collected.</p>
            <Metric label="Coverage status" value={liveIndex?.status.replace('_', ' ') || EMPTY_VALUE} />
          </div>
        </DashboardCard>
      </div>
    );
  }

  if (pageId === 'cpi') {
    return (
      <div className="grid gap-4 xl:grid-cols-2">
        <DashboardCard title="HOW APIX SUPPORTS CPI">
          <ol className="space-y-2 text-sm text-slate-700">
            {[
              'Daily airfare observations',
              'Route x booking-window aggregation',
              'Route sub-index calculation',
              'DGCA passenger-traffic weighting',
              'National APIx',
              'CPI/inflation analysis support',
            ].map((step, index) => (
              <li key={step} className="flex gap-2">
                <span className="font-semibold text-sky-700">{index + 1}.</span>
                <span>{step}</span>
              </li>
            ))}
          </ol>
          <p className="mt-4 text-sm text-slate-600">
            APIx is designed to provide structured airfare information that can support CPI/inflation analysis.
          </p>
        </DashboardCard>
        <DashboardCard title="CURRENT SYSTEM STATUS">
          <div className="grid gap-3 sm:grid-cols-2">
            <Metric label="LIVE coverage" value={`${liveIndex?.coverage.observed_route_window_combinations || 0}/${liveIndex?.coverage.expected_route_window_combinations || routes.length * APPROVED_WINDOWS.length}`} />
            <Metric label="Routes tracked" value={String(routes.length)} />
            <Metric label="Booking windows" value={String(APPROVED_WINDOWS.length)} />
            <Metric label="DGCA weights available" value={routeWeights?.coverage.available === routes.length ? 'Yes' : 'Partial'} />
            <Metric label="National APIx" value={liveIndex?.index_value === null || liveIndex?.index_value === undefined ? 'Unavailable' : formatNumber(liveIndex.index_value)} sublabel="Requires sufficient LIVE coverage" />
            <Metric label="Methodology" value="Observed vs baseline" sublabel="Prototype baseline, not official MoSPI/DGCA" />
          </div>
        </DashboardCard>
      </div>
    );
  }

  if (pageId === 'explorer') {
    return (
      <div className="space-y-4">
        <DashboardCard title="ROUTE WEIGHTS">
          <RouteWeightsTable routes={routes} routeWeights={routeWeights} />
        </DashboardCard>
        <DashboardCard title="LIVE OBSERVATIONS">
          <LiveQuoteTable quotes={liveQuotes} />
        </DashboardCard>
        <DashboardCard title="ROUTE-WINDOW COVERAGE">
          <p className="mb-3 text-xs text-slate-500">
            Coverage indicates whether LIVE fare observations were collected for the route and advance-booking window on the latest collection date. It does not indicate APIx index availability.
          </p>
          <CoverageMatrix routes={routes} coverageByRoute={coverageByRoute} />
        </DashboardCard>
      </div>
    );
  }

  if (pageId === 'reports') {
    const observedCells = liveIndex?.coverage.observed_route_window_combinations || 0;
    const totalCells = liveIndex?.coverage.expected_route_window_combinations || routes.length * APPROVED_WINDOWS.length;
    const sources = liveIndex?.sources_represented.join(', ') || EMPTY_VALUE;

    return (
      <div className="space-y-4">
        <DashboardCard title="DAILY COLLECTION REPORT">
          <div className="grid gap-3 sm:grid-cols-3">
            <Metric label="Collection date" value={latestCollectionDate ? formatDate(latestCollectionDate) : 'No LIVE collection'} />
            <Metric label="Routes targeted" value={String(routes.length)} />
            <Metric label="Windows targeted" value={String(APPROVED_WINDOWS.length)} />
            <Metric label="Total target cells" value={String(totalCells)} />
            <Metric label="LIVE cells" value={`${observedCells}/${totalCells}`} />
            <Metric label="Failed/unavailable cells" value={String(Math.max(0, totalCells - observedCells))} />
            <Metric label="LIVE observations" value={String(liveIndex?.live_quote_count || liveQuotes.length)} />
            <Metric label="Sources contributing" value={sources} />
            <Metric label="National APIx" value="Unavailable" sublabel="Coverage is below the configured threshold" />
          </div>
        </DashboardCard>
        <DashboardCard title="ROUTE COVERAGE TABLE">
          <CoverageMatrix routes={routes} coverageByRoute={coverageByRoute} includeStatus />
        </DashboardCard>
      </div>
    );
  }

  if (pageId === 'settings') {
    return (
      <DashboardCard title="SYSTEM CONFIGURATION & STATUS">
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          <Metric label="Collection frequency" value="Daily" />
          <Metric label="Timezone" value="Asia/Kolkata" />
          <Metric label="Routes" value={`${routes.length} prescribed routes`} />
          <Metric label="Booking windows" value="T+1, T+7, T+15, T+30, T+45" />
          <Metric label="Primary collection mode" value="LIVE" />
          <Metric label="Compliance" value="robots.txt / rate limits" sublabel="Source access checks enabled" />
          <Metric label="Index weighting" value="DGCA passenger-traffic based" />
          <Metric label="Database" value={health?.database || 'Connected'} />
          <Metric label="API" value={health?.status === 'healthy' ? 'Online' : 'Checking service'} />
        </div>
        <p className="mt-4 text-sm text-slate-600">
          Source access failures are logged and handled through compliant failover. CAPTCHA or anti-bot mechanisms are not bypassed.
        </p>
      </DashboardCard>
    );
  }

  return (
    <DashboardCard title={title.toUpperCase()}>
      <EmptyState label={`${title} is available. Apply filters above to keep this view aligned with the current LIVE scope.`} />
    </DashboardCard>
  );
};

interface FilterSelectProps {
  label: string;
  value: string;
  options: Array<{ value: string; label: string; quote_count?: number }>;
  onChange: (value: string) => void;
  emptyLabel?: string;
}

const FilterSelect: React.FC<FilterSelectProps> = ({ label, value, options, onChange, emptyLabel }) => (
  <label className="text-[11px] font-medium text-slate-500">
    {label}
    <select
      value={value}
      onChange={(event) => onChange(event.target.value)}
      className="mt-1 block h-8 min-w-28 rounded-md border border-slate-200 bg-white px-2 text-xs text-slate-800 outline-none focus:border-sky-500"
    >
      <option value="all">All</option>
      {options.length === 0 && emptyLabel ? (
        <option value="none" disabled>{emptyLabel}</option>
      ) : (
        options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}{option.quote_count ? ` (${option.quote_count})` : ''}
          </option>
        ))
      )}
    </select>
  </label>
);

const CompactWindowTable: React.FC<{
  windows: Array<{
    label: string;
    meanFare: number | null;
    baselineFare: number | null;
    subIndex: number | null;
    quotes: number;
    hasData: boolean;
    hasIndexData: boolean;
  }>;
}> = ({ windows }) => (
  <div className="overflow-hidden rounded-md border border-slate-200">
    <table className="w-full text-left text-[11px]">
      <thead className="bg-slate-50 text-slate-500">
        <tr>
          <th className="px-2.5 py-1.5 font-semibold">Window</th>
          <th className="px-2.5 py-1.5 font-semibold">Mean</th>
          <th className="px-2.5 py-1.5 font-semibold">Baseline</th>
          <th className="px-2.5 py-1.5 font-semibold">Index</th>
          <th className="px-2.5 py-1.5 font-semibold">Quotes</th>
        </tr>
      </thead>
      <tbody className="divide-y divide-slate-100">
        {windows.map((window) => (
          <tr key={window.label}>
            <td className="px-2.5 py-1.5 font-semibold text-slate-900">{window.label}</td>
            <td className="px-2.5 py-1.5 text-slate-700">{window.hasData ? formatFare(window.meanFare) : EMPTY_VALUE}</td>
            <td className="px-2.5 py-1.5 text-slate-500">{window.hasData ? formatFare(window.baselineFare) : EMPTY_VALUE}</td>
            <td className={`px-2.5 py-1.5 font-semibold ${window.hasData ? 'text-sky-700' : 'text-slate-400'}`}>
              {window.hasData ? formatNumber(window.subIndex, 1) : EMPTY_VALUE}
            </td>
            <td className="px-2.5 py-1.5 text-slate-500">{window.quotes}</td>
          </tr>
        ))}
      </tbody>
    </table>
  </div>
);

const BookingWindowTable: React.FC<{ windows: RouteWindowBreakdown[] }> = ({ windows }) => (
  <div className="overflow-hidden rounded-md border border-slate-200">
    <table className="w-full text-left text-xs">
      <thead className="bg-slate-50 text-slate-500">
        <tr>
          <th className="px-3 py-2">Window</th>
          <th className="px-3 py-2">Mean fare</th>
          <th className="px-3 py-2">Baseline</th>
          <th className="px-3 py-2">Sub-index</th>
          <th className="px-3 py-2">Quotes</th>
          <th className="px-3 py-2">Status</th>
        </tr>
      </thead>
      <tbody className="divide-y divide-slate-100">
        {windows.map((window) => {
          const hasFareData = window.quotes_count > 0 && isNumber(window.mean_fare);
          const hasIndexData = window.quotes_count > 0 && isIndexDisplayable(window);
          return (
            <tr key={window.advance_window_days}>
              <td className="px-3 py-2 font-semibold text-slate-900">{window.window_label}</td>
              <td className="px-3 py-2">{hasFareData ? formatFare(window.mean_fare) : EMPTY_VALUE}</td>
              <td className="px-3 py-2">{hasIndexData ? formatFare(window.baseline_fare) : EMPTY_VALUE}</td>
              <td className="px-3 py-2 font-semibold">{hasIndexData ? formatNumber(window.sub_index, 1) : EMPTY_VALUE}</td>
              <td className="px-3 py-2">{window.quotes_count}</td>
              <td className="px-3 py-2">{hasIndexData ? 'Index available' : hasFareData ? 'Fare only' : 'Unavailable'}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  </div>
);

const RouteComparisonTable: React.FC<{ routes: RouteItem[]; routeSummaries: RouteSummary[] }> = ({
  routes,
  routeSummaries,
}) => {
  const summaries = new Map(routeSummaries.map((route) => [route.routeCode, route]));

  return (
    <div className="overflow-hidden rounded-md border border-slate-200">
      <table className="w-full text-left text-xs">
        <thead className="bg-slate-50 text-slate-500">
          <tr>
            <th className="px-3 py-2">Route</th>
            <th className="px-3 py-2">Average fare</th>
            <th className="px-3 py-2">Windows</th>
            <th className="px-3 py-2">Quotes</th>
            <th className="px-3 py-2">Status</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {routes.map((route) => {
            const summary = summaries.get(toRouteCode(route));
            return (
              <tr key={route.id}>
                <td className="px-3 py-2 font-semibold text-slate-900">{toRouteCode(route)}</td>
                <td className="px-3 py-2">{summary ? formatFare(summary.avgFare) : EMPTY_VALUE}</td>
                <td className="px-3 py-2">{summary ? `${summary.windowsObserved}/${APPROVED_WINDOWS.length}` : `0/${APPROVED_WINDOWS.length}`}</td>
                <td className="px-3 py-2">{summary?.quoteCount || 0}</td>
                <td className="px-3 py-2">{summary ? 'LIVE observations' : 'Unavailable'}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
};

const RouteWeightsTable: React.FC<{ routes: RouteItem[]; routeWeights: RouteWeightsResponse | null }> = ({
  routes,
  routeWeights,
}) => (
  routes.length === 0 ? (
    <EmptyState
      label="No prescribed route matches the selected filters."
      sublabel="Select a route from the configured DGCA-based route basket."
    />
  ) : (
    <div className="overflow-hidden rounded-md border border-slate-200">
      <table className="w-full text-left text-xs">
        <thead className="bg-slate-50 text-slate-500">
          <tr>
            <th className="px-3 py-2">Route</th>
            <th className="px-3 py-2">Origin</th>
            <th className="px-3 py-2">Destination</th>
            <th className="px-3 py-2">DGCA weight</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {routes.map((route) => (
            <tr key={route.id}>
              <td className="px-3 py-2 font-semibold text-slate-900">{toRouteCode(route)}</td>
              <td className="px-3 py-2">{route.origin_code}</td>
              <td className="px-3 py-2">{route.destination_code}</td>
              <td className="px-3 py-2">{formatDgcaWeight(findRouteWeight(routeWeights, toRouteCode(route)))}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
);

const LiveQuoteTable: React.FC<{ quotes: LiveQuoteItem[] }> = ({ quotes }) => (
  quotes.length === 0 ? (
    <EmptyState label="No persisted LIVE observations match these filters." />
  ) : (
    <div className="overflow-x-auto rounded-md border border-slate-200">
      <table className="min-w-[900px] w-full text-left text-xs">
        <thead className="bg-slate-50 text-slate-500">
          <tr>
            <th className="px-3 py-2">Collection date</th>
            <th className="px-3 py-2">Route</th>
            <th className="px-3 py-2">Source</th>
            <th className="px-3 py-2">Flight</th>
            <th className="px-3 py-2">Departure date</th>
            <th className="px-3 py-2">Window</th>
            <th className="px-3 py-2">Total fare</th>
            <th className="px-3 py-2">Cabin</th>
            <th className="px-3 py-2">Job</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {quotes.map((quote) => (
            <tr key={quote.quote_id}>
              <td className="px-3 py-2">{quoteCollectionDate(quote)}</td>
              <td className="px-3 py-2 font-semibold text-slate-900">{quote.route}</td>
              <td className="px-3 py-2">{quote.source}</td>
              <td className="px-3 py-2">{quote.flight_number || EMPTY_VALUE}</td>
              <td className="px-3 py-2">{quoteDepartureDate(quote)}</td>
              <td className="px-3 py-2">T+{quote.advance_window_days}</td>
              <td className="px-3 py-2 font-semibold">{formatFare(quote.total_fare)}</td>
              <td className="px-3 py-2">{quote.cabin_class || EMPTY_VALUE}</td>
              <td className="px-3 py-2">{quote.scraping_job_id ? `#${quote.scraping_job_id}` : EMPTY_VALUE}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
);

const CoverageMatrix: React.FC<{
  routes: RouteItem[];
  coverageByRoute: Map<string, Set<number>>;
  includeStatus?: boolean;
}> = ({ routes, coverageByRoute, includeStatus = false }) => (
  routes.length === 0 ? (
    <EmptyState
      label="No prescribed route matches the selected filters."
      sublabel="Select a route from the configured DGCA-based route basket."
    />
  ) : (
    <div className="overflow-hidden rounded-md border border-slate-200">
      <table className="w-full text-left text-xs">
        <thead className="bg-slate-50 text-slate-500">
          <tr>
            <th className="px-3 py-2">Route</th>
            {APPROVED_WINDOWS.map((window) => (
              <th key={window} className="px-3 py-2">T+{window}</th>
            ))}
            {includeStatus && <th className="px-3 py-2">Status</th>}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {routes.map((route) => {
            const routeCode = toRouteCode(route);
            const coveredWindows = coverageByRoute.get(routeCode) || new Set<number>();
            return (
              <tr key={route.id}>
                <td className="px-3 py-2 font-semibold text-slate-900">{routeCode}</td>
                {APPROVED_WINDOWS.map((window) => {
                  const hasData = coveredWindows.has(window);
                  return (
                    <td key={window} className={`px-3 py-2 font-semibold ${hasData ? 'text-emerald-700' : 'text-slate-400'}`}>
                      {hasData ? 'Observed' : EMPTY_VALUE}
                    </td>
                  );
                })}
                {includeStatus && (
                  <td className="px-3 py-2">
                    {coveredWindows.size === APPROVED_WINDOWS.length ? 'Complete' : `${coveredWindows.size}/${APPROVED_WINDOWS.length} windows`}
                  </td>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  )
);

const StatusLine: React.FC<{ tone: 'error'; label: string }> = ({ label }) => (
  <div className="flex items-center gap-2 text-rose-700">
    <AlertCircle className="h-3.5 w-3.5" />
    {label}
  </div>
);

interface KpiCardProps {
  label: string;
  value: string;
  sublabel: string;
  tone: 'blue' | 'green' | 'slate' | 'indigo' | 'amber';
}

const toneStyles: Record<KpiCardProps['tone'], string> = {
  blue: 'border-l-sky-500',
  green: 'border-l-emerald-500',
  slate: 'border-l-slate-500',
  indigo: 'border-l-indigo-500',
  amber: 'border-l-amber-500',
};

const KpiCard: React.FC<KpiCardProps> = ({ label, value, sublabel, tone }) => (
  <div className={`rounded-md border border-l-4 border-slate-200 bg-white px-3 py-2.5 shadow-sm ${toneStyles[tone]}`}>
    <div className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">{label}</div>
    <div className="mt-0.5 truncate text-lg font-bold tracking-normal text-slate-950">{value}</div>
    <div className="mt-0.5 truncate text-[11px] text-slate-500">{sublabel}</div>
  </div>
);

interface DashboardCardProps {
  title: string;
  children: React.ReactNode;
  className?: string;
}

const DashboardCard: React.FC<DashboardCardProps> = ({ title, children, className = '' }) => (
  <section className={`rounded-md border border-slate-200 bg-white p-3.5 shadow-sm ${className}`}>
    <div className="mb-2.5 flex items-center justify-between">
      <h2 className="text-xs font-bold uppercase tracking-wide text-slate-800">{title}</h2>
      <Circle className="h-2.5 w-2.5 fill-sky-500 text-sky-500" />
    </div>
    {children}
  </section>
);

const LoadingState: React.FC<{ label: string }> = ({ label }) => (
  <div className="flex h-36 items-center justify-center rounded-md bg-slate-50 text-sm text-slate-500">
    <RefreshCw className="mr-2 h-4 w-4 animate-spin text-sky-600" />
    {label}
  </div>
);

const EmptyState: React.FC<{ label: string; sublabel?: string }> = ({ label, sublabel }) => (
  <div className="flex h-36 items-center justify-center rounded-md bg-slate-50 px-4 text-center text-sm text-slate-500">
    <div>
      <div className="font-medium text-slate-700">{label}</div>
      {sublabel && <div className="mt-1 text-xs text-slate-500">{sublabel}</div>}
    </div>
  </div>
);

const SingleObservation: React.FC<{ date: string; value: number }> = ({ date, value }) => (
  <div className="flex h-40 items-center justify-center rounded-md bg-slate-50 px-5 text-center">
    <div>
      <BarChart3 className="mx-auto mb-2 h-6 w-6 text-sky-600" />
      <div className="text-3xl font-bold text-slate-950">{value.toFixed(2)}</div>
      <div className="mt-1 text-xs font-medium text-slate-500">Observation date: {date}</div>
      <div className="mt-2 text-sm text-slate-700">More observations required for trend analysis</div>
    </div>
  </div>
);

const Metric: React.FC<{ label: string; value: string; sublabel?: string }> = ({ label, value, sublabel }) => (
  <div className="rounded-md bg-slate-50 px-3 py-2">
    <div className="text-[10px] font-medium uppercase tracking-wide text-slate-500">{label}</div>
    <div className="mt-0.5 truncate text-sm font-bold text-slate-900">{value}</div>
    {sublabel && <div className="mt-0.5 text-[11px] text-slate-500">{sublabel}</div>}
  </div>
);
