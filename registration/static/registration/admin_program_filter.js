(function () {
    "use strict";

    function repopulateProgramSelect(programSelect, programs, keepSelectedId, emptyLabel) {
        var currentValue = keepSelectedId != null ? String(keepSelectedId) : programSelect.value;
        programSelect.innerHTML = "";
        if (emptyLabel !== null) {
            var emptyOpt = document.createElement("option");
            emptyOpt.value = "";
            emptyOpt.textContent = emptyLabel;
            programSelect.appendChild(emptyOpt);
        }
        programs.forEach(function (p) {
            var opt = document.createElement("option");
            opt.value = p.id;
            opt.textContent = p.name;
            if (String(p.id) === currentValue) {
                opt.selected = true;
            }
            programSelect.appendChild(opt);
        });
    }

    function wireUp(triggerSelect, programSelect, urlBase, emptyLabel) {
        if (!triggerSelect || !programSelect) return;

        function refresh() {
            var triggerId = triggerSelect.value;
            var keepId = programSelect.getAttribute("data-initial-value");
            programSelect.removeAttribute("data-initial-value");
            if (!triggerId) {
                repopulateProgramSelect(programSelect, [], keepId, emptyLabel);
                return;
            }
            fetch(urlBase + triggerId + "/")
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    repopulateProgramSelect(programSelect, data.programs, keepId, emptyLabel);
                })
                .catch(function () { /* ถ้าเน็ตขัดข้อง ปล่อยรายการเดิมไว้ */ });
        }

        programSelect.setAttribute("data-initial-value", programSelect.value);
        triggerSelect.addEventListener("change", refresh);
        if (triggerSelect.value) {
            refresh();
        }
    }

    document.addEventListener("DOMContentLoaded", function () {
        // หน้า Section: filter Program ตามภาควิชาของ OpenClass (subject) ที่เลือก
        wireUp(
            document.getElementById("id_open_class"),
            document.getElementById("id_program"),
            "/admin/registration/section/programs-for-openclass/",
            "ทุกภาค (ไม่ล็อก)"
        );

        // หน้า Student: filter Program ตามภาควิชาของ Curriculum ที่เลือก
        wireUp(
            document.getElementById("id_curriculum"),
            document.getElementById("id_program"),
            "/admin/registration/student/programs-for-curriculum/",
            null
        );
    });
})();
