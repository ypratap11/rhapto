import { Board } from "@/components/pipeline/Board";
import { Breadcrumbs } from "@/components/shell/Breadcrumbs";

export default function PipelineBoardPage() {
  return (
    <>
      <Breadcrumbs items={[{ label: "Pipeline", href: "/pipeline" }, { label: "Board" }]} />
      <Board />
    </>
  );
}
