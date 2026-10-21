import { Moon, Sun } from "lucide-react";
import { useTheme } from "../../lib/theme";
import { Button } from "../ui/button";

export function ThemeToggle() {
  const { resolved, toggle } = useTheme();
  return (
    <Button
      variant="ghost"
      size="icon"
      onClick={toggle}
      aria-label={`Switch to ${resolved === "dark" ? "light" : "dark"} theme`}
      title={`Switch to ${resolved === "dark" ? "light" : "dark"} theme`}
    >
      {resolved === "dark" ? (
        <Sun className="h-4 w-4" aria-hidden />
      ) : (
        <Moon className="h-4 w-4" aria-hidden />
      )}
    </Button>
  );
}
