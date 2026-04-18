import { ApiClient } from "@/lib/api/client";

describe("ApiClient", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("serializes query params for GET requests", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ items: [], page: 2, page_size: 20, total: 0 }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const client = new ApiClient({ baseUrl: "http://127.0.0.1:8000" });

    await client.get("/tickets", {
      page: 2,
      has_draft: true,
      query: "billing support",
      ignored: undefined,
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8000/tickets?page=2&has_draft=true&query=billing+support",
      expect.objectContaining({
        method: "GET",
        headers: expect.objectContaining({
          Accept: "application/json",
        }),
      }),
    );
  });

  it("raises structured api errors", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          error: {
            code: "validation_error",
            message: "Invalid query parameter.",
            details: { query: "page" },
          },
        }),
        {
          status: 422,
          headers: { "Content-Type": "application/json" },
        },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    const client = new ApiClient({ baseUrl: "http://127.0.0.1:8000" });

    await expect(client.get("/tickets", { page: 0 })).rejects.toMatchObject({
      status: 422,
      code: "validation_error",
      details: { query: "page" },
    });
  });
});
