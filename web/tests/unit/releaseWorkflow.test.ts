import { readFileSync } from "node:fs";
import { resolve } from "node:path";

describe("release source link", () => {
  it("binds both the public link and its smoke assertion to the approved release tag", () => {
    const workflow = readFileSync(resolve(process.cwd(), "../.github/workflows/release-pages.yml"), "utf8");
    const immutableSource =
      "${{ github.server_url }}/${{ github.repository }}/tree/${{ needs.guard.outputs.release_tag }}";

    const sharedChecks = readFileSync(
      resolve(process.cwd(), "../.github/actions/release-checks/action.yml"),
      "utf8",
    );
    expect(workflow).toContain("uses: ./.github/actions/release-checks");
    expect(workflow).toContain(`source-url: ${immutableSource}`);
    expect(sharedChecks).toContain("VITE_SOURCE_URL: ${{ inputs.source-url }}");
    expect(sharedChecks).toContain("PLATEGAUGE_EXPECTED_SOURCE_URL: ${{ inputs.source-url }}");
    expect(workflow).not.toContain(
      "VITE_SOURCE_URL: ${{ github.server_url }}/${{ github.repository }}\n",
    );
  });

  it("preserves the audited distribution and verifies the live site after deployment", () => {
    const workflow = readFileSync(
      resolve(process.cwd(), "../.github/workflows/release-pages.yml"),
      "utf8",
    );

    expect(workflow).toContain("approved-static-dist-${{ needs.guard.outputs.release_tag }}");
    expect(workflow).toContain("retention-days: 90");
    expect(workflow).toContain("needs: [guard, deploy]");
    expect(workflow).toContain(
      "Verify every deployed file is byte-identical to the audited artifact",
    );
    expect(workflow).toContain("cmp --silent");
    expect(workflow).toContain("pnpm test:public-smoke");
  });

  it("fails closed when the weekly public URL is missing or not HTTPS", () => {
    const workflow = readFileSync(
      resolve(process.cwd(), "../.github/workflows/weekly-smoke.yml"),
      "utf8",
    );
    const config = readFileSync(
      resolve(process.cwd(), "playwright.public-smoke.config.ts"),
      "utf8",
    );

    expect(workflow).not.toContain("if: vars.PLATEGAUGE_PUBLIC_URL != ''");
    expect(workflow).toContain('test -n "$PUBLIC_URL"');
    expect(workflow).toContain("PLATEGAUGE_PUBLIC_URL must use HTTPS");
    expect(workflow).toContain("cmp --silent");
    expect(config).toContain('url.protocol !== "https:"');
  });
});
