import React, { useState, useEffect } from 'react';
import { Link, useNavigate, useLocation, data } from 'react-router-dom';
import { signOut } from 'firebase/auth';
import { auth, db } from '../firebase';
import { doc, setDoc, getDoc } from "firebase/firestore";


export default function Navbar({ user }) {
  const navigate = useNavigate();
  const location = useLocation();
  const [loginPrompt, setLoginPrompt] = useState(false);
  const [showUpgradeModal, setShowUpgradeModal] = useState(false);
  const [razorpayLoaded, setRazorpayLoaded] = useState(false);
  const [loadingUserData, setLoadingUserData] = useState(false);
  const [userData, setUserData] = useState(null);

  //const API_URL = "http://localhost:8001";
  //const API_URL = "https://qpg-4e99a2de660c.herokuapp.com";
  const API_URL = "https://www.qnagenai.com";

  const fetchUserData = async () => {
    if (auth.currentUser) {
      setLoadingUserData(true);
      const userDoc = await getDoc(doc(db, "users", auth.currentUser.uid));
      if (userDoc.exists()) {
        setUserData(userDoc.data());
      }
      setLoadingUserData(false);
    }
  };

  const handleUpgradeClick = async () => {
    await fetchUserData();
    setShowUpgradeModal(true);
  };

  const handleLogout = async () => {
    try {
      await signOut(auth);
      navigate('/auth');
    } catch (error) {
      console.error('Logout error:', error);
    }
  };

  useEffect(() => {
    const loadRazorpay = () => {
        const script = document.createElement('script');
        script.src = 'https://checkout.razorpay.com/v1/checkout.js';
        script.onload = () => setRazorpayLoaded(true);
        script.onerror = () => console.error('Failed to load Razorpay script');
        document.body.appendChild(script);
    };

    loadRazorpay();
  }, []);

  const handlePayClick = async () => {
    if (!user) {
      setLoginPrompt(true);
    } else {
      try {
        const response = await fetch(`${API_URL}/api/create-order`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            amount: 99,  // Amount to be paid (₹49)
            user_email: user.email,
          }),
        });

        const data = await response.json();

        if (data.order_id) {
          const options = {
            key: "rzp_live_sUjXQAPMu88qE5", // Replace with your Razorpay Key ID
            amount: data.amount * 100, // Amount in paise
            currency: "INR",
            name: "QnA GenAi",
            description: "Upgrade to Premium Plan",
            order_id: data.order_id,
            handler: async function (response) {
              // Payment successful
              const expiryDate = new Date();
              expiryDate.setMonth(expiryDate.getMonth() + 1); // Add 1 month

                    // Update Firestore
              await setDoc(doc(db, "users", user.uid), {
                subscriptionExpires: expiryDate,
                credits: 25 // no need for credit now
              }, { merge: true }); // Merge to avoid overwriting other fields
              // Handle payment success here, maybe update the user status to subscribed
              alert("Payment Successful! Order ID: " + response.razorpay_order_id);
              window.location.reload();
            },
            prefill: {
              name: 'User Name',
              email: user.email,
            },
            notes: {
              address: "Your address",
            },
          };

          const rzp = new window.Razorpay(options);
          rzp.open();
        } else {
          alert("Error: Could not create Razorpay order.");
        }
      } catch (error) {
        console.error("Payment error:", error);
        alert("Payment error, please try again.");
      }
    }
  };

  useEffect(() => {
    // Close modal on route change
    setShowUpgradeModal(false);
  }, [location.pathname]);

  const initial = user?.email ? user.email.charAt(0).toUpperCase() : '';

  return (
    <>
      <nav className="navbar navbar-dark bg-primary fixed-top shadow-sm">
        <div className="container-fluid d-flex justify-content-between align-items-center">
          <Link to="/app" className="navbar-brand fw-bold">
           QnA genAi
          </Link>

          <button
            type="button"
            className="btn btn-warning"
            data-bs-toggle="modal"
            data-bs-target="#upgradeModal"
            onClick={handleUpgradeClick} // reset login prompt
          >
            Upgrade Plan
          </button>

          {!user ? (
            <Link to="/auth" className="btn btn-light">
              Sign In
            </Link>
          ) : (
            <div className="dropdown">
              <button
                className="avatar-circle p-0"
                type="button"
                id="profileMenu"
                data-bs-toggle="dropdown"
                aria-expanded="false"
              >
                {initial}
              </button>
              <ul className="dropdown-menu dropdown-menu-end" aria-labelledby="profileMenu">
                <li>
                  <button className="dropdown-item" onClick={handleLogout}>
                    Logout
                  </button>
                </li>
              </ul>
            </div>
          )}
        </div>
      </nav>

      {/* Upgrade Modal */}
      <div className="modal fade" id="upgradeModal" tabIndex="-1" aria-hidden="true">
        <div className="modal-dialog modal-dialog-centered modal-lg">
          <div className="modal-content">

            <div className="modal-header">
              <h5 className="modal-title">Choose Your Plan</h5>
              <button type="button" className="btn-close" data-bs-dismiss="modal" aria-label="Close" />
            </div>

            <div className="modal-body">
              {/* Login Prompt Section */}
              {loginPrompt && (
                <div className="alert alert-warning d-flex justify-content-between align-items-center">
                  <span>Please sign in to proceed with payment.</span>
                </div>
              )}

              {userData?.subscriptionExpires && (new Date(userData.subscriptionExpires.seconds * 1000) > new Date(Date.now())) && (
                <div className="alert alert-success d-flex justify-content-between align-items-center">
                  <span>
                    Credits : <strong>{userData.credits}</strong>
                  </span>
                  <span>                  
                    Valid till: <strong>
                    {new Date(userData.subscriptionExpires.seconds * 1000).toLocaleDateString('en-IN')}
                    </strong>
                  </span>
                </div>
              )}

              <div className="row g-4">
                {/* Free Trial Plan */}
                <div className="col-md-6">
                  <div className="card h-100">
                    <div className="card-body d-flex flex-column">
                      <h5 className="card-title">Free Trial</h5>
                      <p className="card-text flex-grow-1">
                      <span style={{ color: 'orange' }}>•</span> Start for free with <strong>1 Credit</strong>. <br/>
                      <span style={{ color: 'orange' }}>•</span> 1 credit = 1 question generate. <br/>
                      <span style={{ color: 'orange' }}>•</span>  Quick and easy access.<br/>
                      <span style={{ color: 'orange' }}>•</span> Explore with your free trial.<br/>
                      <span style={{ color: 'orange' }}>•</span> Ideal for first-time users.<br/>
                      </p>
                    </div>
                  </div>
                </div>

                {/* Upgrade Plan */}
                <div className="col-md-6">
                  <div className="card h-100">
                    <div className="card-body d-flex flex-column">
                      <h5 className="card-title">Upgrade Plan</h5>
                      <p className="card-text flex-grow-1">
                        <strong>₹99</strong> &nbsp;/ Month.<br />
                        Please Upgrade and get <strong>20 Credits!</strong>.
                      </p>
                      <p>
                      <span style={{ color: 'orange' }}>•</span>   Get access for 20 question paper<br />
                      <span style={{ color: 'orange' }}>•</span>   1 month validity.<br />
                      <span style={{ color: 'orange' }}>•</span>   Priority support for subscribers.<br />
                      <span style={{ color: 'orange' }}>•</span>   Stay updated with new features.<br />
                      </p>
                      <p>
                        <strong>Special Offer !!!!</strong>
                        <br /> Upgrade before {new Date(new Date(Date.now()).setDate(new Date(Date.now()).getDate() + 7)).toLocaleDateString('en-IN')} and get <strong>extra 5 Credits</strong>
                      </p>
                      <button
                        className="btn btn-primary mt-auto"
                        onClick={handlePayClick}
                      >
                        Pay ₹99
                      </button>
                    </div>
                  </div>
                </div>

              </div>
            </div>

          </div>
        </div>
      </div>
    </>
  );
}
