/**
 * InSave Hub — Donation Tier Selector & Payment Gateway Controller
 */
(function () {
  "use strict";

  function initDonationControls() {
    const tierBtns = document.querySelectorAll("[data-donation-amount]");
    const amountInput = document.getElementById("donationAmountInput");
    const anonCheckbox = document.getElementById("donationAnonymousCheck");
    const donorNameGroup = document.getElementById("donorNameGroup");

    if (tierBtns.length && amountInput) {
      tierBtns.forEach((btn) => {
        btn.addEventListener("click", () => {
          tierBtns.forEach((b) => b.classList.remove("is-selected"));
          btn.classList.add("is-selected");
          amountInput.value = btn.getAttribute("data-donation-amount") || "";
        });
      });

      amountInput.addEventListener("input", () => {
        const currentVal = amountInput.value.trim();
        tierBtns.forEach((b) => {
          if (b.getAttribute("data-donation-amount") === currentVal) {
            b.classList.add("is-selected");
          } else {
            b.classList.remove("is-selected");
          }
        });
      });
    }

    if (anonCheckbox && donorNameGroup) {
      anonCheckbox.addEventListener("change", () => {
        donorNameGroup.style.opacity = anonCheckbox.checked ? "0.45" : "1";
      });
    }
  }

  document.addEventListener("DOMContentLoaded", initDonationControls);
})();
