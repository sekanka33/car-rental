import { ApiError, apiGet, apiRequest, buildUrl, getApiBaseUrl } from '@/lib/api';
import { Platform } from 'react-native';

const mockFetch = jest.fn();
globalThis.fetch = mockFetch as unknown as typeof fetch;

function jsonResponse(status: number, body: unknown) {
  return { ok: status >= 200 && status < 300, status, json: async () => body } as Response;
}

describe('buildUrl', () => {
  it('uses the Android emulator host when no API URL is configured', () => {
    expect(getApiBaseUrl('android')).toBe('http://10.0.2.2:8000');
  });

  it('routes a configured localhost API URL through the Android emulator host', () => {
    expect(getApiBaseUrl('android', 'http://localhost:8000')).toBe('http://10.0.2.2:8000');
  });

  it('keeps an explicitly configured non-local API URL', () => {
    expect(getApiBaseUrl('android', 'https://api.example.com/')).toBe('https://api.example.com');
  });

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

describe('uploads', () => {
  it('sends a multipart form as-is, without a JSON content type', async () => {
    const originalPlatform = Platform.OS;
    Object.defineProperty(Platform, 'OS', { configurable: true, value: 'web' });
    mockFetch.mockResolvedValueOnce(jsonResponse(201, { id: 'p1' }));
    const form = new FormData();
    form.append('document_type', 'INSURANCE');

    try {
      await apiRequest('POST', '/api/v1/upload', { form, body: { ignored: true } });

      const [, init] = mockFetch.mock.calls[mockFetch.mock.calls.length - 1];
      expect(init.body).toBe(form);
      expect(init.headers['Content-Type']).toBeUndefined();
    } finally {
      Object.defineProperty(Platform, 'OS', { configurable: true, value: originalPlatform });
    }
  });

  it('sends native multipart forms through XMLHttpRequest', async () => {
    const originalPlatform = Platform.OS;
    const originalXhr = globalThis.XMLHttpRequest;
    Object.defineProperty(Platform, 'OS', { configurable: true, value: 'android' });

    class MockXHR {
      static latest: MockXHR;
      onload: (() => void) | null = null;
      onerror: (() => void) | null = null;
      onabort: (() => void) | null = null;
      status = 201;
      responseText = '{"id":"p1"}';
      open = jest.fn();
      setRequestHeader = jest.fn();
      getAllResponseHeaders = jest.fn(() => 'content-type: application/json\r\n');
      send = jest.fn((_body: XMLHttpRequestBodyInit | null) => this.onload?.());
      abort = jest.fn(() => this.onabort?.());

      constructor() {
        MockXHR.latest = this;
      }
    }
    globalThis.XMLHttpRequest = MockXHR as unknown as typeof XMLHttpRequest;
    mockFetch.mockClear();
    const form = new FormData();
    form.append('document_type', 'INSURANCE');

    try {
      await expect(apiRequest('POST', '/api/v1/upload', { form })).resolves.toEqual({ id: 'p1' });
      expect(MockXHR.latest.open).toHaveBeenCalledWith('POST', 'http://localhost:8000/api/v1/upload');
      expect(MockXHR.latest.send).toHaveBeenCalledWith(form);
      expect(mockFetch).not.toHaveBeenCalled();
    } finally {
      globalThis.XMLHttpRequest = originalXhr;
      Object.defineProperty(Platform, 'OS', { configurable: true, value: originalPlatform });
    }
  });
});
