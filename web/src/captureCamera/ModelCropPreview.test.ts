import { createElement } from "react";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import ModelCropPreview from "./ModelCropPreview";
import type { CameraPhoto } from "./camera";

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

function setup() {
  const retained = new Uint8ClampedArray(224 * 224 * 4).fill(127);
  const copied = retained.slice();
  const imageData = { data: new Uint8ClampedArray(copied.length) } as ImageData;
  let drawn: Uint8ClampedArray | undefined;
  const context = {
    createImageData: vi.fn(() => imageData),
    putImageData: vi.fn((image: ImageData) => { drawn = image.data.slice(); }),
    clearRect: vi.fn(),
  };
  const contextSpy = vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(context as unknown as CanvasRenderingContext2D);
  const photo = { url: "blob:unused-full-frame", width: 640, height: 480, copyPixels: vi.fn(() => ({ width: 224, height: 224, data: copied })), release: vi.fn() } satisfies CameraPhoto;
  return { retained, copied, imageData, context, contextSpy, photo, drawn: () => drawn };
}

describe("model crop review", () => {
  it("renders exact retained model pixels, wipes temporary copies, and clears on unmount", () => {
    const fixture = setup();
    const view = render(createElement(ModelCropPreview, { photo: fixture.photo, label: "Before model view" }));
    expect(screen.getByRole("img", { name: "Before model view" })).toBeVisible();
    expect(view.container.querySelector("img")).toBeNull();
    expect(fixture.drawn()).toEqual(fixture.retained);
    expect(fixture.copied.every((value) => value === 0)).toBe(true);
    expect(fixture.imageData.data.every((value) => value === 0)).toBe(true);
    expect(fixture.retained.every((value) => value === 127)).toBe(true);
    view.unmount();
    expect(fixture.context.clearRect).toHaveBeenCalledWith(0, 0, 224, 224);
    expect(fixture.photo.release).not.toHaveBeenCalled();
  });
  it("clears and redraws when the selected photo changes", () => {
    const fixture = setup();
    const view = render(createElement(ModelCropPreview, { photo: fixture.photo, label: "Before model view" }));
    const next = { ...fixture.photo, copyPixels: vi.fn(() => ({ width: 224, height: 224, data: new Uint8ClampedArray(224 * 224 * 4).fill(99) })) };
    view.rerender(createElement(ModelCropPreview, { photo: next, label: "After model view" }));
    expect(fixture.context.clearRect).toHaveBeenCalledTimes(1);
    expect(fixture.context.putImageData).toHaveBeenCalledTimes(2);
    expect(fixture.drawn()?.every((value) => value === 99)).toBe(true);
  });
  it("shows a recoverable message if Canvas is unavailable", () => {
    const fixture = setup();
    fixture.contextSpy.mockReturnValue(null);
    render(createElement(ModelCropPreview, { photo: fixture.photo, label: "Before model view" }));
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    expect(screen.getByText(/Model view unavailable/)).toBeVisible();
    expect(fixture.photo.copyPixels).not.toHaveBeenCalled();
  });
  it("does not expose a partial preview after a released photo fails", () => {
    const fixture = setup();
    vi.mocked(fixture.photo.copyPixels).mockImplementation(() => { throw new Error("Released"); });
    render(createElement(ModelCropPreview, { photo: fixture.photo, label: "Before model view" }));
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    expect(screen.getByText(/Model view unavailable/)).toBeVisible();
    expect(fixture.context.clearRect).toHaveBeenCalled();
  });
  it("rejects unexpected dimensions and wipes that temporary copy", () => {
    const fixture = setup();
    vi.mocked(fixture.photo.copyPixels).mockReturnValue({ width: 640, height: 480, data: fixture.copied });
    render(createElement(ModelCropPreview, { photo: fixture.photo, label: "Before model view" }));
    expect(fixture.context.putImageData).not.toHaveBeenCalled();
    expect(fixture.copied.every((value) => value === 0)).toBe(true);
    expect(screen.getByText(/Model view unavailable/)).toBeVisible();
  });
});
