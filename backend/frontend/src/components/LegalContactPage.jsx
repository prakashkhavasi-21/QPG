// src/components/LegalContactPage.jsx

import React from 'react';

const tiles = [
  {
    title: 'Terms and Conditions',
    content: `By using this platform, you agree to abide by our terms and conditions.
              Please use the platform responsibly. We reserve the right to modify or terminate services at any time.
              Additionally, please note that since our platform leverages OpenAI GPT-4.0, the information provided is 
              based on data available up to December 2023. Any content generated may not reflect developments or information 
              released after that date.
              The platform does not support any regional languages.
              The platform is intended for educational purposes only. We are not responsible for any misuse of the generated content.`,
  },
  {
    title: 'Cancellations and Refunds',
    content: `We understand that sometimes you may need to cancel your subscription. You can cancel your order under the following conditions:
              To request a cancellation, please contact us immediately at qnagenai@gmail.com or call our support line with your email and valid reason for cancellation.
              You can cancel your order under the following conditions: you are eligible to cancel the subscription within 24 hours of payment done so the user will get 80% refund.
              If the user cancels the subscription after 24 hours day of payment, the user will not get any refund.
              If you have any questions or concerns regarding our cancellation policy, please feel free to reach out to us.`,
  },
  {
    title: 'Privacy Policy',
    content: `We are committed to protecting your privacy. Your personal data is handled 
    securely and is not shared with third parties without consent. Please refer to our full privacy policy for details.`,
  },
  {
    title: 'Contact Us',
    content: (
      <div className="space-y-2 text-sm">
        <p>
          <strong>Email:</strong>{' '}
          <a href="mailto:qnagenai@gmail.com" className="text-blue-600 underline">
            qnagenai@gmail.com
          </a>
        </p>
        <p>
          <strong>Phone:</strong>{' '}
          <a href="tel:+918050903058" className="text-blue-600 underline">
            +91 8050903058
          </a>
        </p>
        <p><strong>Address:</strong> Near Padma Hospital, Devaraj Nagar, Terdal - 587315, Karnataka</p>
        <a
          href="https://wa.me/918050903058"
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center px-4 py-2 bg-green-500 text-white rounded hover:bg-green-600"
        >
          📲 Chat on WhatsApp
        </a>
      </div>
    ),
  },
];

const LegalContactPage = () => {
  return (
    <div className="container my-5 pt-5 px-3 md:px-0" style={{ minHeight: '100vh' }}>
      <h1 className="text-3xl font-bold mb-6 text-center">Legal & Contact Information</h1>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {tiles.map((tile, index) => (
          <div
            key={index}
            className="p-6 border rounded shadow hover:shadow-lg transition duration-200 bg-white break-words"
          >
            <h2 className="text-xl font-semibold mb-3">{tile.title}</h2>
            <div className="text-gray-700 text-sm space-y-2">{tile.content}</div>
          </div>
        ))}
      </div>
    </div>
  );
};

export default LegalContactPage;
