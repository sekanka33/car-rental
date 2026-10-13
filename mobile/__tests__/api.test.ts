import { ApiError, apiGet, buildUrl } from '@/lib/api';

const mockFetch = jest.fn();
globalThis.fetch = mockFetch as unknown as typeof fetch;

function jsonResponse(status: number, body: unknown) {
  return { ok: status >= 200 && status < 300, status, json: async () => body } as Response;
}

describe('buildUrl', () => {
  it('drops empty parameters and encodes values', () => {
    expect(buildUrl('/api/v1/vehicles', { q: 'polo vivo', transmission: undefined, city: '', limit: 20 })).toBe(
      'http://localhost:8000/api/v1/vehicles?q=polo%20vivo&limit=20',
    );
  });
});

describe('apiGet', () => {
  it('returns parsed JSON', async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse(200, { items: [], total: 0 }));

    await expect(apiGet('/api/v1/vehicles')).resolves.toEqual({ items: [], total: 0 });
    expect(mockFetch).toHaveBeenCalledWith('http://localhost:8000/api/v1/vehicles', expect.anything());
  });

  it('turns the backend error envelope into an ApiError', async () => {
    mockFetch.mockResolvedValueOnce(
      jsonResponse(404, { error: { code: 'not_found', message: 'Vehicle not found.' } }),
    );

    const error = (await apiGet('/api/v1/vehicles/x').catch((e: unknown) => e)) as ApiError;
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 404, code: 'not_found', message: 'Vehicle not found.' });
    expect(error.isNotFound).toBe(true);
  });

  it('handles non-JSON error pages', async () => {
    mockFetch.mockResolvedValueOnce({ ok: false, status: 502, json: async () => JSON.parse('<html>') } as Response);

    await expect(apiGet('/x')).rejects.toMatchObject({ status: 502, code: 'http_error' });
  });

  it('reports network failures', async () => {
    mockFetch.mockRejectedValueOnce(new TypeError('Network request failed'));

    await expect(apiGet('/x')).rejects.toMatchObject({ status: 0, code: 'network_error' });
  });

  it('reports timeouts', async () => {
    mockFetch.mockImplementationOnce(
      (_url: string, init: RequestInit) =>
        new Promise((_resolve, reject) => {
          init.signal?.addEventListener('abort', () => {
            const abort = new Error('aborted');
            abort.name = 'AbortError';
            reject(abort);
          });
        }),
    );

    await expect(apiGet('/x', undefined, { timeoutMs: 10 })).rejects.toMatchObject({ code: 'timeout' });
  });
});
