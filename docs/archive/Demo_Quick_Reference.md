# 🎯 Mailwright Demo - Quick Reference Card

## 🚀 **Quick Start (5 Minutes)**

### 1️⃣ **Pre-Demo Setup**
```bash
# Start Mailwright server
python -m mailwright.main

# Verify in browser: http://localhost:8000/docs
```

### 2️⃣ **Postman Setup**
- Import: `Mailwright_Demo_Collection.postman_collection.json`
- Import: `Mailwright_Demo_Environment.postman_environment.json`
- Set Environment: "Mailwright Demo Environment"

### 3️⃣ **Demo Execution Order**

#### **Phase A: System Check (30 seconds)**
1. ✅ Health Check
2. ✅ Root Endpoint  
3. ✅ Access SwaggerUI Documentation

#### **Phase B: Template Creation (2 minutes)**
4. 🎯 Create Template - TechCorp Welcome
5. 🚀 Create Template - Startup Launch (Advanced)
6. 🛒 Create Template - E-commerce Holiday Sale
7. ❓ Create Template - Vague Brief (Triggers Clarification)

#### **Phase C: Status Monitoring (1 minute)**
8. 📊 Get Template Status - Primary
9. 📊 Get Status - Alternative Template
10. 📊 Get Status - Clarification Template

⏱️ **Wait 30-60 seconds for AI processing**

#### **Phase D: Version Management (2 minutes)**
11. 📋 List All Versions *(This populates version IDs)*
12. 🖼️ Preview HTML (Current Version)
13. 📝 Get MJML Source

#### **Phase E: Clarification & Feedback (2 minutes)**
14. 🤖 Submit Amended Brief (Clarification Response)
15. 💬 Submit Feedback - Make it Casual
16. 💬 Submit Feedback - Add Testimonial
17. ✅ Approve Template Version

---

## 🎭 **Demo Talking Points**

### **Template Creation**
> "Watch how Mailwright instantly accepts the brief and starts processing with our LangGraph workflow. The 202 response means our AI agents are now working in the background."

### **Status Monitoring**
> "The status endpoint shows real-time progress. Notice how the template moves through different states as our AI agents complete their work."

### **Clarification Workflow**
> "When the brief is vague, Mailwright's AI automatically detects this and requests clarification - just like a real marketing professional would."

### **Image Generation**
> "Behind the scenes, DALL-E is generating custom images based on the brief content and brand requirements."

### **Feedback Loop**
> "The iterative refinement process allows for multiple rounds of feedback, with AI understanding context and making intelligent improvements."

---

## 🔧 **Common Demo Issues & Quick Fixes**

| Issue | Quick Fix | Reason |
|-------|-----------|---------|
| 404 on version endpoints | Run "List All Versions" first | Version ID not populated yet |
| Empty version_id | Wait 30-60 seconds, then refresh status | Templates need time to process |
| Template still processing | Show the status monitoring - part of the demo! | AI workflow takes time |
| No MJML content | Check if template creation succeeded | Template may have failed |
| Tests failing but 202 responses | Normal - templates created but versions pending | Processing time expected |

### 🚨 **NEW: Automatic Error Handling**
The collection now includes **smart error handling** that:
- ✅ Detects missing version IDs automatically
- ✅ Provides clear guidance in console logs  
- ✅ Gracefully handles 404s during processing
- ✅ Shows appropriate test results for demo flow

---

## 💡 **Pro Demo Tips**

1. **Show the Console** - Postman console has rich logging
2. **Explain the Timing** - AI processing is part of the value prop
3. **Multiple Templates** - Run different industry examples
4. **Real-time Status** - Refresh status to show live updates
5. **Version History** - Demonstrate version management capabilities

---

## 📊 **Expected Results Summary**

- ✅ **14+ Successful Tests** (Core functionality)
- ⏱️ **2-5 Second** Template Creation Response
- 🧠 **10-30 Second** AI Processing Time  
- 📈 **Multiple Versions** Per Template
- 🎨 **Generated Images** in MJML Output
- 📧 **Production-Ready** HTML Email Templates

---

*Total Demo Time: ~8-10 minutes for full walkthrough* 