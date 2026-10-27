import { render,screen } from "@testing-library/react";
import { beforeEach,describe,expect,it,vi } from "vitest";
import DescriptionsPage from "@/app/projects/[projectId]/sources/[sourceId]/frames/descriptions/page";
import { getDescriptions } from "@/lib/api/descriptions";
import { getVisualGallery } from "@/lib/api/visuals";
import { ApiError } from "@/lib/api/errors";
import { descriptionFixture } from "../../../../../../../../test-support/description-fixture";
import { projectId,sourceId,visualFixture } from "../../../../../../../../test-support/visual-fixture";
import { parseDescriptionView } from "@/lib/api/description-contracts";
vi.mock("@/lib/api/descriptions",()=>({getDescriptions:vi.fn()}));
vi.mock("@/lib/api/visuals",()=>({getVisualGallery:vi.fn()}));
vi.mock("@/app/actions/descriptions",()=>({describeFramesAction:vi.fn()}));
vi.mock("next/navigation",()=>({notFound:()=>{throw new Error("not-found");},useRouter:()=>({refresh:vi.fn()})}));
function page(source=sourceId) {return DescriptionsPage({params:Promise.resolve({projectId,sourceId:source})});}
describe("description page",()=>{
  beforeEach(()=>{vi.clearAllMocks();vi.mocked(getDescriptions).mockResolvedValue(parseDescriptionView(descriptionFixture()));vi.mocked(getVisualGallery).mockResolvedValue(visualFixture());});
  it("joins only the same complete gallery before rendering",async()=>{
    render(await page());
    expect(getDescriptions).toHaveBeenCalledWith(projectId,sourceId);
    expect(screen.getByRole("heading",{name:"Local image-model descriptions"})).toBeVisible();
  });
  it("rejects invalid ids before reads",async()=>{
    await expect(page("../foreign")).rejects.toThrow("not-found");expect(getDescriptions).not.toHaveBeenCalled();
  });
  it("offers a safe refresh on a changed gallery instead of associating wrong frames",async()=>{
    vi.mocked(getVisualGallery).mockResolvedValue({...visualFixture(),generation:8});
    render(await page());expect(screen.getByRole("alert")).toHaveTextContent("could not load");expect(screen.queryByRole("img")).toBeNull();
  });
  it("hides missing scope and private upstream errors",async()=>{
    vi.mocked(getDescriptions).mockRejectedValue(new ApiError({status:404}));await expect(page()).rejects.toThrow("not-found");
    vi.mocked(getDescriptions).mockRejectedValue(new ApiError({status:503,message:"PRIVATE"}));render(await page());
    expect(screen.getByRole("alert")).not.toHaveTextContent("PRIVATE");
  });
});
