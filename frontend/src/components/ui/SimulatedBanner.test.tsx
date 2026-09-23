import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { SimulatedBanner } from "./SimulatedBanner";
import { render } from "@testing-library/react";

describe("SimulatedBanner", () => {
  it("renders an unmistakable simulated label", () => {
    render(<SimulatedBanner />);
    expect(screen.getByTestId("simulated-banner")).toHaveTextContent(/Simulated — not a real model output/i);
  });
});
