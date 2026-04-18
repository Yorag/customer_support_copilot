import "@testing-library/jest-dom/vitest";

const originalWarn = console.warn;

vi.spyOn(console, "warn").mockImplementation((message, ...args) => {
  if (
    typeof message === "string" &&
    message.includes("React Router Future Flag Warning")
  ) {
    return;
  }

  originalWarn(message, ...args);
});
