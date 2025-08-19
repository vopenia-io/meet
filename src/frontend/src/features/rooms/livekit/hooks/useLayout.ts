import {useSnapshot} from "valtio";
import {layoutStore} from "@/stores/layout.ts";


export const useLayout = () => {

  const layoutSnap = useSnapshot(layoutStore)


  const displaySubtitle = (enable: boolean) => {
    layoutStore.showSubtitle = enable
  }

  const toggleSubtitle = () => {
    layoutStore.showSubtitle = !layoutSnap.showSubtitle
  }

  return {
    isSubtitleOpen: layoutSnap.showSubtitle,
    displaySubtitle,
    toggleSubtitle
  }
}
