// /**
//  * Email Finder - Main JavaScript
//  */

// document.addEventListener('DOMContentLoaded', function() {
//     // Form submission handling with loading indicator
//     const form = document.querySelector('form');
//     if (form) {
//         form.addEventListener('submit', function() {
//             showLoadingOverlay();
//         });
//     }

//     // Copy email to clipboard functionality
//     setupCopyEmailButtons();
// });

// /**
//  * Shows the loading overlay when form is submitted
//  */
// function showLoadingOverlay() {
//     const overlay = document.createElement('div');
//     overlay.className = 'loading-overlay';
//     overlay.innerHTML = `
//         <div class="spinner-border text-primary spinner" role="status">
//             <span class="visually-hidden">Loading...</span>
//         </div>
//     `;
//     document.body.appendChild(overlay);
// }

// /**
//  * Sets up the copy to clipboard functionality for email addresses
//  */
// function setupCopyEmailButtons() {
//     const copyButtons = document.querySelectorAll('.copy-email');
    
//     copyButtons.forEach(button => {
//         button.addEventListener('click', function() {
//             const email = this.getAttribute('data-email');
            
//             navigator.clipboard.writeText(email).then(() => {
//                 // Change button text temporarily
//                 const originalText = this.innerHTML;
//                 this.innerHTML = '<i class="bi bi-check-lg"></i> Copied!';
                
//                 setTimeout(() => {
//                     this.innerHTML = originalText;
//                 }, 2000);
//             }).catch(err => {
//                 console.error('Could not copy text: ', err);
//                 alert('Failed to copy email. Please try again.');
//             });
//         });
//     });
// }

// /**
//  * Validates a LinkedIn URL
//  */
// function validateLinkedInUrl(url) {
//     const regex = /^(https?:\/\/)?(www\.)?linkedin\.com\/in\/[\w\-\_\%]+\/?$/;
//     return regex.test(url);
// }

// // Add event listener to validate LinkedIn URL on input
// document.addEventListener('DOMContentLoaded', function() {
//     const linkedInUrlInput = document.getElementById('linkedin_url');
//     const submitButton = document.querySelector('button[type="submit"]');
    
//     if (linkedInUrlInput && submitButton) {
//         linkedInUrlInput.addEventListener('input', function() {
//             const url = this.value.trim();
//             if (url && !validateLinkedInUrl(url)) {
//                 this.classList.add('is-invalid');
//                 if (!this.nextElementSibling || !this.nextElementSibling.classList.contains('invalid-feedback')) {
//                     const feedback = document.createElement('div');
//                     feedback.className = 'invalid-feedback';
//                     feedback.textContent = 'Please enter a valid LinkedIn profile URL';
//                     this.parentNode.insertBefore(feedback, this.nextSibling);
//                 }
//                 submitButton.disabled = true;
//             } else {
//                 this.classList.remove('is-invalid');
//                 if (this.nextElementSibling && this.nextElementSibling.classList.contains('invalid-feedback')) {
//                     this.nextElementSibling.remove();
//                 }
//                 submitButton.disabled = false;
//             }
//         });
//     }
// });
