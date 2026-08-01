"use client";

/** Arabic/English UI strings with RTL/LTR direction handling.
 *
 * Arabic is the default: the product is Arabic-first. The chosen locale drives
 * `dir` and `lang` on <html>, which is what makes Tailwind's logical utilities
 * (ps-*, me-*, text-start) flip automatically.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

export type Locale = "ar" | "en";
export type Dir = "rtl" | "ltr";

const LOCALE_KEY = "aseelo.locale";

const STRINGS = {
  // ---- generic ----
  appTagline: { ar: "من الفكرة إلى المحتوى", en: "From Idea to Content" },
  loading: { ar: "جارٍ التحميل…", en: "Loading…" },
  save: { ar: "حفظ", en: "Save" },
  saving: { ar: "جارٍ الحفظ…", en: "Saving…" },
  saved: { ar: "تم الحفظ", en: "Saved" },
  cancel: { ar: "إلغاء", en: "Cancel" },
  delete: { ar: "حذف", en: "Delete" },
  retry: { ar: "إعادة المحاولة", en: "Retry" },
  optional: { ar: "اختياري", en: "optional" },
  somethingWrong: { ar: "حدث خطأ ما", en: "Something went wrong" },

  // ---- auth ----
  login: { ar: "تسجيل الدخول", en: "Log in" },
  loginTitle: { ar: "تسجيل الدخول", en: "Welcome back" },
  loginSubtitle: {
    ar: "سجّل الدخول للمتابعة إلى حسابك",
    en: "Log in to continue to your account",
  },
  register: { ar: "إنشاء حساب", en: "Create account" },
  registerTitle: { ar: "إنشاء حساب جديد", en: "Create your account" },
  registerSubtitle: {
    ar: "ابدأ بإنشاء فيديوهات تحمل هويتك التجارية",
    en: "Start creating videos with your own brand",
  },
  name: { ar: "الاسم", en: "Name" },
  email: { ar: "البريد الإلكتروني", en: "Email" },
  password: { ar: "كلمة المرور", en: "Password" },
  confirmPassword: { ar: "تأكيد كلمة المرور", en: "Confirm password" },
  forgotPassword: { ar: "نسيت كلمة المرور؟", en: "Forgot password?" },
  noAccount: { ar: "ليس لديك حساب؟", en: "No account yet?" },
  haveAccount: { ar: "لديك حساب بالفعل؟", en: "Already have an account?" },
  logout: { ar: "تسجيل الخروج", en: "Log out" },
  passwordsDoNotMatch: { ar: "كلمتا المرور غير متطابقتين", en: "Passwords do not match" },
  passwordTooShort: {
    ar: "كلمة المرور يجب ألا تقل عن ٨ أحرف",
    en: "Password must be at least 8 characters",
  },
  forgotPasswordTitle: { ar: "استعادة كلمة المرور", en: "Reset your password" },
  forgotPasswordSubtitle: {
    ar: "أدخل بريدك الإلكتروني وسنرسل لك رابطاً لإعادة التعيين.",
    en: "Enter your email and we'll send you a reset link.",
  },
  sendResetLink: { ar: "إرسال الرابط", en: "Send reset link" },
  // Deliberately non-committal: the API does not reveal whether the address is
  // registered, so this copy must not either.
  resetLinkSent: {
    ar: "إن كان هناك حساب بهذا البريد، فقد أُرسل إليه رابط لإعادة التعيين. تحقّق من بريدك.",
    en: "If an account exists for that address, a reset link has been sent. Check your inbox.",
  },
  backToLogin: { ar: "العودة لتسجيل الدخول", en: "Back to sign in" },
  resetPasswordTitle: { ar: "تعيين كلمة مرور جديدة", en: "Set a new password" },
  resetPasswordSubtitle: {
    ar: "اختر كلمة مرور جديدة لحسابك.",
    en: "Choose a new password for your account.",
  },
  newPassword: { ar: "كلمة المرور الجديدة", en: "New password" },
  resetPasswordSubmit: { ar: "حفظ كلمة المرور", en: "Save password" },
  resetPasswordDone: {
    ar: "تم تغيير كلمة المرور. يمكنك تسجيل الدخول الآن.",
    en: "Your password has been changed. You can sign in now.",
  },
  resetTokenMissing: {
    ar: "الرابط غير صالح أو ناقص. اطلب رابطاً جديداً.",
    en: "This link is invalid or incomplete. Request a new one.",
  },

  // ---- nav ----
  dashboard: { ar: "لوحة التحكم", en: "Dashboard" },
  brand: { ar: "الهوية التجارية", en: "Brand" },
  videos: { ar: "مكتبة الفيديو", en: "Videos" },
  createVideo: { ar: "إنشاء فيديو", en: "Create video" },
  settings: { ar: "الإعدادات", en: "Settings" },

  // ---- dashboard ----
  welcome: { ar: "أهلاً", en: "Welcome" },
  dashboardSubtitle: {
    ar: "حوّل فيديوهاتك إلى ريلز جاهزة للنشر بهويتك التجارية",
    en: "Turn your clips into ready-to-post Reels with your brand",
  },
  totalVideos: { ar: "إجمالي الفيديوهات", en: "Total videos" },
  videosToday: { ar: "فيديوهات اليوم", en: "Today" },
  processingJobs: { ar: "قيد المعالجة", en: "Processing" },
  storageUsed: { ar: "المساحة المستخدمة", en: "Storage used" },
  recentVideos: { ar: "أحدث الفيديوهات", en: "Recent videos" },
  viewAll: { ar: "عرض الكل", en: "View all" },
  noVideosYet: { ar: "لا توجد فيديوهات بعد", en: "No videos yet" },
  noVideosYetHelp: {
    ar: "أنشئ أول فيديو لك وسيظهر هنا",
    en: "Create your first video and it will appear here",
  },

  // ---- brand ----
  brandSubtitle: {
    ar: "تُطبَّق هذه الهوية تلقائياً على كل فيديو تنشئه",
    en: "This identity is applied automatically to every video you create",
  },
  brandName: { ar: "اسم العلامة التجارية", en: "Brand name" },
  logo: { ar: "الشعار", en: "Logo" },
  uploadLogo: { ar: "رفع شعار", en: "Upload logo" },
  changeLogo: { ar: "تغيير الشعار", en: "Change logo" },
  logoHint: { ar: "PNG أو JPG أو WEBP، حتى ٥ ميجابايت", en: "PNG, JPG or WEBP, up to 5 MB" },
  colors: { ar: "الألوان", en: "Colours" },
  primaryColor: { ar: "اللون الأساسي", en: "Primary" },
  secondaryColor: { ar: "اللون الثانوي", en: "Secondary" },
  accentColor: { ar: "لون التمييز", en: "Accent" },
  contactInfo: { ar: "معلومات التواصل", en: "Contact information" },
  phone: { ar: "الهاتف", en: "Phone" },
  whatsapp: { ar: "واتساب", en: "WhatsApp" },
  website: { ar: "الموقع الإلكتروني", en: "Website" },
  address: { ar: "العنوان", en: "Address" },
  tagline: { ar: "الشعار النصي", en: "Tagline" },

  // ---- create ----
  createSubtitle: {
    ar: "اكتب النص، ارفع الفيديو، واختر القالب",
    en: "Enter your text, upload a clip, pick a template",
  },
  videoTitle: { ar: "عنوان الفيديو", en: "Video title" },
  videoText: { ar: "النص الظاهر في الفيديو", en: "Text shown in the video" },
  videoTextHint: {
    ar: "يدعم العربية والإنجليزية والنص المختلط",
    en: "Supports Arabic, English and mixed text",
  },
  sourceVideo: { ar: "ملف الفيديو", en: "Video file" },
  chooseFile: { ar: "اختر ملفاً", en: "Choose a file" },
  dropHint: {
    ar: "MP4 أو MOV أو MKV — من ١ إلى ١٨٠ ثانية، حتى ٥١٢ ميجابايت",
    en: "MP4, MOV or MKV — 1 to 180 seconds, up to 512 MB",
  },
  template: { ar: "القالب", en: "Template" },
  submitCreate: { ar: "إنشاء الفيديو", en: "Create video" },
  uploading: { ar: "جارٍ الرفع…", en: "Uploading…" },
  textRequired: { ar: "النص مطلوب", en: "Text is required" },
  fileRequired: { ar: "يجب اختيار ملف فيديو", en: "Please choose a video file" },
  templateRequired: { ar: "يجب اختيار قالب", en: "Please choose a template" },

  // ---- library / detail ----
  filterAll: { ar: "الكل", en: "All" },
  filterProcessing: { ar: "قيد المعالجة", en: "Processing" },
  filterCompleted: { ar: "مكتملة", en: "Completed" },
  filterFailed: { ar: "فاشلة", en: "Failed" },
  preview: { ar: "معاينة", en: "Preview" },
  download: { ar: "تنزيل", en: "Download" },
  createAnother: { ar: "إنشاء فيديو جديد", en: "Create new video" },
  processingTitle: { ar: "جارٍ إنشاء الفيديو", en: "Creating your video" },
  processingHelp: {
    ar: "يمكنك مغادرة هذه الصفحة — ستستمر المعالجة في الخلفية",
    en: "You can leave this page — processing continues in the background",
  },
  completedTitle: { ar: "فيديوك جاهز", en: "Your video is ready" },
  failedTitle: { ar: "فشلت المعالجة", en: "Rendering failed" },
  duration: { ar: "المدة", en: "Duration" },
  resolution: { ar: "الأبعاد", en: "Resolution" },
  createdAt: { ar: "تاريخ الإنشاء", en: "Created" },
  fileSize: { ar: "حجم الملف", en: "File size" },
  confirmDelete: {
    ar: "هل تريد حذف هذا الفيديو نهائياً؟",
    en: "Delete this video permanently?",
  },
  backToVideos: { ar: "العودة إلى المكتبة", en: "Back to videos" },
  notFound: { ar: "الفيديو غير موجود", en: "Video not found" },

  // ---- settings ----
  account: { ar: "الحساب", en: "Account" },
  language: { ar: "اللغة", en: "Language" },
  memberSince: { ar: "عضو منذ", en: "Member since" },
  role: { ar: "الصلاحية", en: "Role" },

  // ---- PWA ----
  installTitle: { ar: "ثبّت التطبيق", en: "Install the app" },
  installBody: {
    ar: "أضف أصيلو إلى شاشتك الرئيسية للوصول السريع والعمل بملء الشاشة",
    en: "Add ASEELO to your home screen for quick, full-screen access",
  },
  install: { ar: "تثبيت", en: "Install" },
  installed: { ar: "تم تثبيت التطبيق", en: "App installed" },
  dismiss: { ar: "إخفاء", en: "Dismiss" },
  installIosBody: {
    ar: "افتح قائمة المشاركة ثم اختر «إضافة إلى الشاشة الرئيسية»",
    en: "Open the Share menu, then choose “Add to Home Screen”",
  },
  offlineBanner: {
    ar: "لا يوجد اتصال بالإنترنت — بعض الإجراءات لن تعمل",
    en: "You are offline — some actions will not work",
  },
  backOnline: { ar: "عاد الاتصال", en: "Back online" },
  updateAvailable: { ar: "يتوفّر إصدار جديد", en: "A new version is available" },
  updateNow: { ar: "تحديث", en: "Refresh" },
  appSection: { ar: "التطبيق", en: "App" },
  installState: { ar: "حالة التثبيت", en: "Installation" },
  runningStandalone: { ar: "مُثبَّت", en: "Installed" },
  runningInBrowser: { ar: "يعمل في المتصفح", en: "Running in browser" },
} as const;

export type StringKey = keyof typeof STRINGS;

interface I18nValue {
  locale: Locale;
  dir: Dir;
  setLocale: (locale: Locale) => void;
  t: (key: StringKey) => string;
}

const I18nContext = createContext<I18nValue | null>(null);

export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>("ar");

  useEffect(() => {
    const stored = window.localStorage.getItem(LOCALE_KEY);
    if (stored === "ar" || stored === "en") setLocaleState(stored);
  }, []);

  useEffect(() => {
    const dir: Dir = locale === "ar" ? "rtl" : "ltr";
    document.documentElement.lang = locale;
    document.documentElement.dir = dir;
  }, [locale]);

  const setLocale = useCallback((next: Locale) => {
    setLocaleState(next);
    window.localStorage.setItem(LOCALE_KEY, next);
  }, []);

  const value = useMemo<I18nValue>(
    () => ({
      locale,
      dir: locale === "ar" ? "rtl" : "ltr",
      setLocale,
      t: (key) => STRINGS[key][locale],
    }),
    [locale, setLocale],
  );

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nValue {
  const context = useContext(I18nContext);
  if (!context) throw new Error("useI18n must be used inside <I18nProvider>");
  return context;
}
