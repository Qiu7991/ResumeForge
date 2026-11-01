import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import PartialDateInput from "./PartialDateInput";

describe("PartialDateInput", () => {
  it("直接输入年月，失焦后归一化为 YYYY-MM", () => {
    const onChange = vi.fn();
    render(<PartialDateInput label="开始时间" value="" onChange={onChange} />);
    const input = screen.getByLabelText("开始时间（年-月 或 年-月-日）");
    fireEvent.change(input, { target: { value: "2022年9月" } });
    fireEvent.blur(input);
    expect(onChange).toHaveBeenLastCalledWith("2022-09");
  });

  it("只填年份保留年份；输入中文日期也能归一化", () => {
    const onChange = vi.fn();
    render(<PartialDateInput label="毕业时间" value="" onChange={onChange} />);
    const input = screen.getByLabelText("毕业时间（年-月 或 年-月-日）");
    fireEvent.change(input, { target: { value: "2026" } });
    fireEvent.blur(input);
    expect(onChange).toHaveBeenLastCalledWith("2026");
    fireEvent.change(input, { target: { value: "2026年6月15日" } });
    fireEvent.blur(input);
    expect(onChange).toHaveBeenLastCalledWith("2026-06-15");
  });

  it("至今只给区间结束端，取消后恢复上一个具体日期", () => {
    const onChange = vi.fn();
    const { rerender } = render(
      <PartialDateInput label="结束时间" value="2026-07" onChange={onChange} allowOngoing />,
    );
    const checkbox = screen.getByRole("checkbox", { name: "至今" });
    fireEvent.click(checkbox);
    expect(onChange).toHaveBeenLastCalledWith("至今");
    rerender(<PartialDateInput label="结束时间" value="至今" onChange={onChange} allowOngoing />);
    fireEvent.click(screen.getByRole("checkbox", { name: "至今" }));
    expect(onChange).toHaveBeenLastCalledWith("2026-07");
  });
});
