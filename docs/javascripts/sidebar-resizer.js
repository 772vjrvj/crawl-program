(() => {
    const STORAGE_KEY = "crawl-program-sidebar-width";

    const DEFAULT_WIDTH = 360;
    const MIN_WIDTH = 240;
    const MAX_WIDTH = 700;

    function clamp(value, min, max) {
        return Math.min(Math.max(value, min), max);
    }

    function setSidebarWidth(width) {
        const safeWidth = clamp(width, MIN_WIDTH, MAX_WIDTH);

        document.documentElement.style.setProperty(
            "--project-tree-width",
            `${safeWidth}px`
        );

        return safeWidth;
    }

    function getSavedWidth() {
        const savedValue = Number(localStorage.getItem(STORAGE_KEY));

        if (!Number.isFinite(savedValue)) {
            return DEFAULT_WIDTH;
        }

        return clamp(savedValue, MIN_WIDTH, MAX_WIDTH);
    }

    function initializeSidebarResizer() {
        if (window.innerWidth < 1220) {
            return;
        }

        const mainContainer = document.querySelector(".md-main__inner.md-grid");
        const primarySidebar = document.querySelector(".md-sidebar--primary");

        if (!mainContainer || !primarySidebar) {
            return;
        }

        // MkDocs의 페이지 전환 과정에서 중복 생성 방지
        const existingResizer = mainContainer.querySelector(
            ".md-sidebar-resizer"
        );

        if (existingResizer) {
            existingResizer.remove();
        }

        setSidebarWidth(getSavedWidth());

        const resizer = document.createElement("div");

        resizer.className = "md-sidebar-resizer";
        resizer.setAttribute("role", "separator");
        resizer.setAttribute("aria-label", "왼쪽 문서 트리 너비 조절");
        resizer.setAttribute("aria-orientation", "vertical");
        resizer.title = "드래그하여 왼쪽 트리 너비 조절";

        primarySidebar.insertAdjacentElement("afterend", resizer);

        let isDragging = false;

        function startDragging(event) {
            event.preventDefault();

            isDragging = true;

            document.body.classList.add("is-sidebar-resizing");
            resizer.classList.add("is-dragging");
        }

        function resizeSidebar(event) {
            if (!isDragging) {
                return;
            }

            const mainRect = mainContainer.getBoundingClientRect();
            const requestedWidth = event.clientX - mainRect.left;
            const appliedWidth = setSidebarWidth(requestedWidth);

            resizer.setAttribute("aria-valuenow", String(appliedWidth));
        }

        function stopDragging() {
            if (!isDragging) {
                return;
            }

            isDragging = false;

            document.body.classList.remove("is-sidebar-resizing");
            resizer.classList.remove("is-dragging");

            const currentWidth = parseInt(
                getComputedStyle(document.documentElement)
                    .getPropertyValue("--project-tree-width"),
                10
            );

            if (Number.isFinite(currentWidth)) {
                localStorage.setItem(STORAGE_KEY, String(currentWidth));
            }
        }

        function resetSidebarWidth() {
            const width = setSidebarWidth(DEFAULT_WIDTH);

            localStorage.setItem(STORAGE_KEY, String(width));
            resizer.setAttribute("aria-valuenow", String(width));
        }

        resizer.addEventListener("mousedown", startDragging);
        resizer.addEventListener("dblclick", resetSidebarWidth);

        document.addEventListener("mousemove", resizeSidebar);
        document.addEventListener("mouseup", stopDragging);

        resizer.setAttribute("aria-valuemin", String(MIN_WIDTH));
        resizer.setAttribute("aria-valuemax", String(MAX_WIDTH));
        resizer.setAttribute("aria-valuenow", String(getSavedWidth()));
    }

    /*
     * 최초 페이지 실행
     */
    document.addEventListener("DOMContentLoaded", initializeSidebarResizer);

    /*
     * MkDocs Material의 instant navigation을 사용하는 경우
     */
    if (typeof document$ !== "undefined") {
        document$.subscribe(initializeSidebarResizer);
    }
})();