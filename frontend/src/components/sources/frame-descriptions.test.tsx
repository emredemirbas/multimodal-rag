import { render,screen } from "@testing-library/react";
import { describe,expect,it,vi } from "vitest";
import { FrameDescriptions } from "@/components/sources/frame-descriptions";
import { VisualProvenance } from "@/components/sources/visual-provenance";
import { parseDescriptionView } from "@/lib/api/description-contracts";
import { descriptionFixture } from "../../../test-support/description-fixture";
import { projectId,visualFixture } from "../../../test-support/visual-fixture";
vi.mock("next/navigation",()=>({useRouter:()=>({refresh:vi.fn()})}));
vi.mock("@/app/actions/descriptions",()=>({describeFramesAction:vi.fn()}));
describe("unreviewed retained image descriptions",()=>{
  it("renders escaped interpretations, uncertainties, separate OCR and pinned provenance",()=>{
    render(<FrameDescriptions projectId={projectId} gallery={visualFixture()} view={parseDescriptionView(descriptionFixture())} requestKey="stable-fixture-key"/>);
    expect(screen.getByRole("heading",{name:"Unreviewed image-model interpretation"})).toBeVisible();
    expect(screen.getByText(/<script>PRIVATE<\/script>/)).toBeVisible();
    expect(screen.getByText("Purpose is unknown.")).toBeVisible();
    expect(screen.getByRole("heading",{name:"Separate literal OCR"})).toBeVisible();
    expect(screen.getByRole("region",{name:"Image-model description provenance"})).toHaveTextContent("qwen3.5:4b");
    expect(document.querySelector("script,video,audio,iframe")).toBeNull();
    expect(screen.getByRole("button",{name:"Describe retained frames"})).toBeEnabled();
  });
  it("shows disabled, partial, failed, busy and abstention states honestly",()=>{
    const raw=descriptionFixture(),view=parseDescriptionView({...raw,enabled:false,origin:null,items:[],index_job:null,gallery_generation:null,index_generation:null});
    const {rerender}=render(<FrameDescriptions projectId={projectId} gallery={visualFixture()} view={view} requestKey="fixture-key"/>);
    expect(screen.queryByRole("button",{name:"Describe retained frames"})).toBeNull();
    expect(screen.getByText(/Private partial results are not shown/)).toBeVisible();
    const pending=parseDescriptionView({...raw,latest_job:{...raw.latest_job,id:projectId,generation:5,status:"running"}});
    rerender(<FrameDescriptions projectId={projectId} gallery={visualFixture()} view={pending} requestKey="fixture-key"/>);
    expect(screen.getByRole("button",{name:"Describe retained frames"})).toBeDisabled();
    expect(screen.getByText(/earlier complete snapshot/)).toBeVisible();
    rerender(<FrameDescriptions projectId={projectId} gallery={visualFixture()} view={{...pending,latest_job:{...pending.latest_job!,status:"failed"}}} requestKey="fixture-key"/>);
    expect(screen.getByRole("alert")).toHaveTextContent("Existing evidence is unchanged");
    const abstained=structuredClone(raw);Object.assign(abstained.items[0].description,{kind:"unclear",summary:"",details:[],abstained:true});
    rerender(<FrameDescriptions projectId={projectId} gallery={visualFixture()} view={parseDescriptionView(abstained)} requestKey="fixture-key"/>);
    expect(screen.getByText(/The model abstained/)).toBeVisible();
  });
  it("labels mixed citations without claiming verified facts or image understanding for old OCR",()=>{
    const {rerender}=render(<VisualProvenance origin={{...visualFixture().origin!,description:descriptionFixture().origin}}/>);
    expect(screen.getByText(/model interpretations, not verified facts or speech/)).toBeVisible();
    expect(screen.getByText(/Description generation 3/)).toHaveTextContent("retained-frame-description-v1");
    rerender(<VisualProvenance origin={visualFixture().origin}/>);
    expect(screen.getByText(/not speech or image understanding/)).toBeVisible();
  });
});
