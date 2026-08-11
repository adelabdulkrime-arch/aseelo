import { render } from "@testing-library/react";
import type { ReactElement } from "react";

import { I18nProvider } from "@/lib/i18n";

/** Pages resolve their copy through useI18n, so they need the real provider.
 *
 * Deliberately not stubbed: rendering the genuine strings means the tests
 * exercise the Arabic default the product actually ships, rather than English
 * placeholders no user ever sees.
 */
export function renderPage(ui: ReactElement) {
  return render(<I18nProvider>{ui}</I18nProvider>);
}

/** Copy under test, so a string change fails loudly in one place. */
export const AR = {
  email: "البريد الإلكتروني",
  password: "كلمة المرور",
  confirmPassword: "تأكيد كلمة المرور",
  choosePassword: "اختر كلمة المرور",
  name: "الاسم",
  login: "تسجيل الدخول",
  register: "إنشاء حساب",
  saveAndProceed: "حفظ ومتابعة",
  somethingWrong: "حدث خطأ ما",
  passwordsDoNotMatch: "كلمتا المرور غير متطابقتين",
  passwordTooShort: "كلمة المرور يجب ألا تقل عن ٨ أحرف",
} as const;
