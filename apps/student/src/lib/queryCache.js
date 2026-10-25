// Shared request cache + in-flight de-duplication for the student portal.
//
// Why this exists: `useQuery` creates one fetch per hook call, and nothing is
// shared between hook instances. The dashboard mounts DashboardOverview,
// StageIndicator, TopNav and ReminderWindow at once — and `useDeadlineCompletion`
// silently expands into four more queries — so a single page load fired ~31
// requests for 9 distinct endpoints (/me six times, /team four times, …).
// Routing every read through here collapses that to one request per endpoint.
//
// Deliberately tiny and dependency-free: dedup + TTL only, no subscriptions,
// no background revalidation. Reach for a real data layer (TanStack Query) if
// this ever needs cross-component invalidation.

export const DEFAULT_TTL_MS = 5000;

/** key -> { at, value } — last successful response. Failures are never stored. */
const entries = new Map();
/** key -> Promise — a request currently on the wire. */
const inflight = new Map();

/**
 * Fetch `key`, reusing an in-flight request or a fresh cached value.
 *
 * @param {string}   key      cache key — the request path
 * @param {Function} fetcher  called only on a real miss; must return a Promise
 * @param {object}   [opts]
 * @param {number}   [opts.ttl=DEFAULT_TTL_MS]  how long a value stays fresh
 * @param {boolean}  [opts.force=false]  skip the cache (explicit refetch/poll)
 * @param {number}   [opts.now=Date.now()]  injectable clock, for tests
 */
export function getOrFetch(key, fetcher, opts = {}) {
  const { ttl = DEFAULT_TTL_MS, force = false, now = Date.now() } = opts;

  // Always join an in-flight request, even when forcing: two components polling
  // on the same tick should still produce a single round-trip.
  const pending = inflight.get(key);
  if (pending) return pending;

  if (!force) {
    const hit = entries.get(key);
    if (hit && now - hit.at < ttl) return Promise.resolve(hit.value);
  }

  const request = Promise.resolve()
    .then(fetcher)
    .then((value) => {
      // Cache only successes — a cached rejection would poison the whole TTL
      // window for every component sharing this key.
      entries.set(key, { at: opts.now === undefined ? Date.now() : now, value });
      return value;
    })
    .finally(() => {
      inflight.delete(key);
    });

  inflight.set(key, request);
  return request;
}

/** Drop one key's cached value (its next read hits the network). */
export function invalidateQuery(key) {
  entries.delete(key);
}

/** Drop everything. Call on logout / session expiry so the next user starts clean. */
export function clearQueryCache() {
  entries.clear();
  inflight.clear();
}
