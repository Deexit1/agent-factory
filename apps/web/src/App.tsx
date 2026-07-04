import { BoardPage } from "./board/BoardPage";
import { ActorProvider } from "./auth/ActorContext";

export function App(): React.JSX.Element {
  return (
    <ActorProvider>
      <BoardPage />
    </ActorProvider>
  );
}
