import { Link } from "react-router-dom";
import { ThemeToggle } from "@/components/ThemeToggle";

export default function PrivacyPage() {
  return (
    <div className="min-h-screen bg-paper-50 px-4 py-8 text-ink-900 dark:bg-ink-950 dark:text-paper-100">
      <article className="mx-auto max-w-3xl space-y-8">
        <header className="flex items-start justify-between gap-4 border-b border-ink-800/15 pb-5 dark:border-paper-100/10">
          <div>
            <p className="text-sm font-medium text-accent">Teacher Helper</p>
            <h1 className="mt-1 text-3xl font-bold">Polityka prywatności</h1>
            <p className="mt-2 text-sm text-ink-600 dark:text-paper-400">Wersja 1.0 · obowiązuje od 13 września 2026 r.</p>
          </div>
          <ThemeToggle />
        </header>

        <section className="space-y-3">
          <h2 className="text-xl font-semibold">Administrator i kontakt</h2>
          <p>Administratorem Teacher Helper jest Filip Mazurkiewicz. W sprawach prywatności napisz na <a className="text-accent underline" href="mailto:fifmazurkiewicz@gmail.com">fifmazurkiewicz@gmail.com</a>.</p>
          <p className="text-sm text-ink-600 dark:text-paper-400">Ten dokument opisuje działanie Teacher Helper pod adresem teacherhelper.fmazurkiewicz.dev.</p>
        </section>

        <section className="space-y-3">
          <h2 className="text-xl font-semibold">Jakie dane przetwarzamy</h2>
          <ul className="list-disc space-y-2 pl-6">
            <li>Dane konta: adres e-mail, opcjonalna nazwa wyświetlana, rola i status akceptacji.</li>
            <li>Rozmowy, polecenia, odpowiedzi AI oraz informacje o utworzonych projektach i materiałach.</li>
            <li>Przesłane pliki, ich tekstowe fragmenty i wektory używane do wyszukiwania właściwego kontekstu.</li>
            <li>Dane techniczne, bezpieczeństwa i użycia modeli potrzebne do działania usługi, limitów kosztu i diagnozowania problemów.</li>
          </ul>
        </section>

        <section className="space-y-3">
          <h2 className="text-xl font-semibold">Cel i podstawa</h2>
          <p>Dane konta i materiały przetwarzamy w celu świadczenia żądanej usługi. Dane bezpieczeństwa i ograniczone logi techniczne przetwarzamy w prawnie uzasadnionym interesie ochrony, utrzymania i rozliczalności systemu. Jeżeli w przyszłości uruchomimy opcjonalne analityki wymagające zgody, nie zostaną aktywowane przed jej udzieleniem.</p>
        </section>

        <section className="space-y-3">
          <h2 className="text-xl font-semibold">AI i odbiorcy danych</h2>
          <p>Teacher Helper korzysta z generatywnej AI. Do dostawcy modelu wysyłamy polecenie, niezbędny kontekst rozmowy i tylko trafne fragmenty wybranych materiałów. Odpowiedzi mogą być błędne, stronnicze, niepełne lub nieodpowiednie dla wieku ucznia i wymagają sprawdzenia przez nauczyciela.</p>
          <p>Usługę obsługują Supabase (uwierzytelnianie, baza i pliki), Render (backend), Vercel (frontend) oraz OpenRouter i wybrani przez niego dostawcy modeli. Zależnie od użytej funkcji dane mogą trafić również do Tavily, KIE, ElevenLabs albo skonfigurowanego dostawcy wideo. Langfuse otrzymuje logi obserwowalności tylko wtedy, gdy administrator włączy tę integrację.</p>
          <p>Niektórzy dostawcy mogą przetwarzać dane poza EOG. Stosujemy mechanizmy transferowe oferowane w ich aktualnych warunkach przetwarzania. Szczegółowe ustawienia produkcyjne i rejestr podmiotów przetwarzających podlegają okresowej weryfikacji.</p>
        </section>

        <section className="space-y-3 rounded-xl border border-amber-500/30 bg-amber-500/10 p-4">
          <h2 className="text-xl font-semibold">Dane uczniów</h2>
          <p>Nie wpisuj prawdziwych imion uczniów, danych kontaktowych, ocen, informacji o niepełnosprawności, zachowaniu ani innych danych pozwalających ich zidentyfikować. Używaj neutralnych oznaczeń, np. „Uczeń A”. Nie przesyłaj danych innej osoby bez odpowiedniego uprawnienia.</p>
        </section>

        <section className="space-y-3">
          <h2 className="text-xl font-semibold">Przechowywanie i Twoje prawa</h2>
          <p>Treści użytkownika przechowujemy podczas aktywnego korzystania z konta, chyba że użytkownik usunie je wcześniej. Zakończone zadania generacji przechowujemy 90 dni, incydenty systemowe 365 dni, a logi użycia modeli 730 dni. Chronione kopie zapasowe wygasają w cyklu właściwego dostawcy. Użytkownik może na bieżąco usuwać rozmowy, projekty i pliki. W Profilu można pobrać kopię danych lub usunąć całe konto.</p>
          <p>Możesz żądać dostępu, sprostowania, usunięcia, ograniczenia, przeniesienia danych lub wnieść sprzeciw, kontaktując się z administratorem. Masz również prawo złożyć skargę do Prezesa Urzędu Ochrony Danych Osobowych.</p>
        </section>

        <section lang="en" className="space-y-6 border-t-2 border-ink-800/15 pt-8 dark:border-paper-100/10">
          <div>
            <p className="text-sm font-medium text-accent">English version</p>
            <h2 className="mt-1 text-2xl font-bold">Privacy Policy</h2>
            <p className="mt-2 text-sm text-ink-600 dark:text-paper-400">Version 1.0 · effective 13 September 2026</p>
          </div>
          <div className="space-y-2">
            <h3 className="text-lg font-semibold">Controller and contact</h3>
            <p>Teacher Helper is controlled by Filip Mazurkiewicz. For privacy matters, contact <a className="text-accent underline" href="mailto:fifmazurkiewicz@gmail.com">fifmazurkiewicz@gmail.com</a>.</p>
          </div>
          <div className="space-y-2">
            <h3 className="text-lg font-semibold">Data and purposes</h3>
            <p>We process account details, conversations, prompts, AI responses, projects, uploaded and generated files, searchable document fragments, and limited technical, security and model-usage records. Account content is processed to provide the requested service. Security and limited operational records are processed to protect, maintain and account for the service.</p>
          </div>
          <div className="space-y-2">
            <h3 className="text-lg font-semibold">AI and service providers</h3>
            <p>Teacher Helper uses generative AI. We send the prompt, necessary conversation context and relevant excerpts from selected materials to the model provider. Results may be inaccurate, biased, incomplete or unsuitable for a student's age and must be reviewed by a teacher.</p>
            <p>The service uses Supabase, Render, Vercel, OpenRouter and its selected model providers. Depending on the requested feature, Tavily, KIE, ElevenLabs, a configured video provider, or Langfuse may also process relevant data. Some providers may process data outside the EEA under the transfer mechanisms in their applicable processing terms.</p>
          </div>
          <div className="space-y-2 rounded-xl border border-amber-500/30 bg-amber-500/10 p-4">
            <h3 className="text-lg font-semibold">Student data</h3>
            <p>Do not enter real student names, contact details, grades, disability information, behavioural notes or other identifying information. Use neutral labels such as “Student A”. Do not submit another person's data without appropriate authority.</p>
          </div>
          <div className="space-y-2">
            <h3 className="text-lg font-semibold">Retention and your rights</h3>
            <p>User content is kept while the account is active unless the user deletes it earlier. Completed generation jobs are retained for 90 days, system incidents for 365 days and model usage records for 730 days. Protected backups expire according to the relevant provider's backup cycle.</p>
            <p>You may request access, correction, deletion, restriction, portability or object to processing by contacting the controller. You may also complain to the Polish data-protection authority. Profile controls let you export your data or delete conversations, materials or the entire account.</p>
          </div>
        </section>

        <footer className="border-t border-ink-800/15 py-6 text-sm dark:border-paper-100/10">
          <Link className="text-accent underline" to="/assistant">Wróć do Teacher Helper</Link>
        </footer>
      </article>
    </div>
  );
}
