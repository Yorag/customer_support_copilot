type QueryValue =
  | string
  | number
  | boolean
  | null
  | undefined
  | Array<string | number | boolean>;

export type ApiQuery = Record<string, QueryValue>;

export type ApiErrorPayload = {
  error?: {
    code?: string;
    message?: string;
    details?: Record<string, unknown>;
  };
};

export class ApiClientError extends Error {
  readonly status: number;
  readonly code?: string;
  readonly details?: Record<string, unknown>;

  constructor(options: {
    message: string;
    status: number;
    code?: string;
    details?: Record<string, unknown>;
  }) {
    super(options.message);
    this.name = "ApiClientError";
    this.status = options.status;
    this.code = options.code;
    this.details = options.details;
  }
}

type RequestOptions = {
  query?: ApiQuery;
  body?: unknown;
  headers?: HeadersInit;
  signal?: AbortSignal;
};

export class ApiClient {
  private readonly baseUrl: string;

  constructor(options: { baseUrl: string }) {
    this.baseUrl = options.baseUrl.replace(/\/+$/, "");
  }

  async get<TResponse>(path: string, query?: ApiQuery, signal?: AbortSignal) {
    return this.request<TResponse>("GET", path, { query, signal });
  }

  async post<TResponse>(
    path: string,
    body?: unknown,
    headers?: HeadersInit,
    signal?: AbortSignal,
  ) {
    return this.request<TResponse>("POST", path, { body, headers, signal });
  }

  private async request<TResponse>(
    method: string,
    path: string,
    options: RequestOptions = {},
  ): Promise<TResponse> {
    const response = await fetch(this.buildUrl(path, options.query), {
      method,
      headers: {
        Accept: "application/json",
        ...(options.body !== undefined ? { "Content-Type": "application/json" } : {}),
        ...options.headers,
      },
      body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
      signal: options.signal,
    });

    const payload = await this.readPayload(response);

    if (!response.ok) {
      const apiError = payload as ApiErrorPayload;
      throw new ApiClientError({
        message: apiError.error?.message ?? `Request failed with status ${response.status}.`,
        status: response.status,
        code: apiError.error?.code,
        details: apiError.error?.details,
      });
    }

    return payload as TResponse;
  }

  private buildUrl(path: string, query?: ApiQuery): string {
    const url = new URL(path, `${this.baseUrl}/`);

    if (!query) {
      return url.toString();
    }

    for (const [key, value] of Object.entries(query)) {
      if (value === undefined || value === null || value === "") {
        continue;
      }

      if (Array.isArray(value)) {
        for (const item of value) {
          url.searchParams.append(key, String(item));
        }
        continue;
      }

      url.searchParams.append(key, String(value));
    }

    return url.toString();
  }

  private async readPayload(response: Response): Promise<unknown> {
    const contentType = response.headers.get("Content-Type") ?? "";

    if (contentType.includes("application/json")) {
      return response.json();
    }

    const text = await response.text();
    return text ? { message: text } : null;
  }
}
