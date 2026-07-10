import { redirect } from "next/navigation";

// F10a: /storm folded into /weather as a lens (nav "Storm" -> "Weather").
// storm-client.tsx stays in place — /weather imports it directly for the
// storm lens — so this route becomes a pure redirect, not a deletion.
export default function Page() {
  redirect("/weather?lens=storm");
}
