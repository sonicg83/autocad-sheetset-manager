// @vitest-environment happy-dom

import {afterEach,describe,expect,it,vi} from "vitest";

import {deleteStandard} from "./standards";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("deleteStandard", () => {
  it("调用服务端定义的 POST 删除端点并携带影响凭证", async () => {
    const standardId = "00000000-0000-4000-8000-000000000046";
    const impactToken = "delete-impact-token";
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({standard_id: standardId, deleted_count: 3}),
    });
    vi.stubGlobal("fetch", fetchMock);

    await deleteStandard(standardId, impactToken);

    expect(fetchMock).toHaveBeenCalledWith(`/api/standards/${standardId}/delete`, {
      headers: {"Content-Type": "application/json"},
      method: "POST",
      body: JSON.stringify({impact_token: impactToken}),
    });
  });
});
