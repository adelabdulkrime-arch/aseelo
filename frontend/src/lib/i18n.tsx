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

  // ---- session errors ----
  sessionRateLimited: {
    ar: "عدد كبير من الجلسات فُتحت من هذا المتصفح خلال فترة قصيرة. حاول مرة أخرى بعد قليل.",
    en: "Too many sessions were started from this browser in a short time. Try again shortly.",
  },
  sessionDisabled: {
    ar: "التطبيق غير متاح للاستخدام حالياً. حاول لاحقاً.",
    en: "The app is not accepting new sessions right now. Please try again later.",
  },
  sessionUnknownError: {
    ar: "تعذّر فتح جلسة جديدة. تحقّق من اتصالك وحاول مرة أخرى.",
    en: "Could not start a session. Check your connection and try again.",
  },

  // ---- shared field labels ----
  name: { ar: "الاسم", en: "Name" },

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
  logoNoTransparency: {
    ar: "شعارك بدون خلفية شفافة — قد يظهر بمربع أبيض. يُفضل استخدام صيغة PNG مفرغة.",
    en: "Your logo has no transparent background — it may show as a white box. A cut-out PNG works best.",
  },
  removeWhiteBackground: { ar: "إزالة الخلفية البيضاء", en: "Remove the white background" },
  removeWhiteBackgroundHint: {
    ar: "قد يزيل الأبيض الموجود داخل التصميم أيضاً.",
    en: "This may also clear white that belongs to the design.",
  },
  logoCutoutApplied: {
    ar: "تمت إزالة الخلفية البيضاء من شعارك.",
    en: "The white background was removed from your logo.",
  },
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
  startOver: { ar: "بدء جلسة جديدة", en: "Start a new session" },
  startOverBody: {
    ar: "هذا يمسح فيديوهاتك وهويتك التجارية الحالية نهائياً ويبدأ بجلسة فارغة.",
    en: "This permanently clears your current videos and brand, and starts a fresh session.",
  },

  // ---- PWA ----
  installTitle: { ar: "ثبّت التطبيق", en: "Install the app" },
  installBody: {
    ar: "أضف في ون ميديا إلى شاشتك الرئيسية للوصول السريع والعمل بملء الشاشة",
    en: "Add V.onemedia to your home screen for quick, full-screen access",
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
