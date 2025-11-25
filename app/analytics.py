"""
Analytics & Monitoring Module with Supabase
ระบบวิเคราะห์และติดตามการใช้งาน (Railway Free Tier Optimized)
ใช้ Supabase เก็บข้อมูล + Dashboard HTML
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import os
from supabase import Client

logger = logging.getLogger(__name__)

# ============================================================================#
# Analytics Tracker with Supabase
# ============================================================================#

class AnalyticsTracker:
    """
    ติดตามสถิติการใช้งานด้วย Supabase
    เก็บข้อมูลใน database เพื่อวิเคราะห์ระยะยาว
    """
    
    def __init__(self, supabase_client: Client):
        self.supabase = supabase_client
        logger.info("✓ Analytics tracker initialized (Supabase)")
    
    async def track_image_analysis(
        self, 
        user_id: str, 
        disease_name: str, 
        pest_type: str = None,
        confidence: str = None,
        severity: str = None,
        response_time_ms: float = 0
    ):
        """บันทึกการวิเคราะห์รูปภาพ"""
        try:
            data = {
                "user_id": user_id,
                "event_type": "image_analysis",
                "disease_name": disease_name,
                "pest_type": pest_type,
                "confidence": confidence,
                "severity": severity,
                "response_time_ms": response_time_ms,
                "created_at": datetime.now().isoformat()
            }
            
            self.supabase.table('analytics_events').insert(data).execute()
            logger.debug(f"✓ Tracked image analysis: {disease_name}")
            
        except Exception as e:
            logger.error(f"Failed to track image analysis: {e}")
    
    async def track_question(
        self, 
        user_id: str, 
        question: str,
        intent: str = None,
        response_time_ms: float = 0
    ):
        """บันทึกคำถาม"""
        try:
            data = {
                "user_id": user_id,
                "event_type": "question",
                "question_text": question[:200],  # จำกัดความยาว
                "intent": intent,
                "response_time_ms": response_time_ms,
                "created_at": datetime.now().isoformat()
            }
            
            self.supabase.table('analytics_events').insert(data).execute()
            logger.debug(f"✓ Tracked question")
            
        except Exception as e:
            logger.error(f"Failed to track question: {e}")
    
    async def track_product_recommendation(
        self, 
        user_id: str,
        disease_name: str,
        products: List[str]
    ):
        """บันทึกการแนะนำผลิตภัณฑ์"""
        try:
            for product_name in products:
                data = {
                    "user_id": user_id,
                    "event_type": "product_recommendation",
                    "disease_name": disease_name,
                    "product_name": product_name,
                    "created_at": datetime.now().isoformat()
                }
                
                self.supabase.table('analytics_events').insert(data).execute()
            
            logger.debug(f"✓ Tracked {len(products)} product recommendations")
            
        except Exception as e:
            logger.error(f"Failed to track product recommendations: {e}")

    async def track_registration(
        self,
        user_id: str,
        success: bool = True
    ):
        """บันทึกการลงทะเบียน"""
        try:
            data = {
                "user_id": user_id,
                "event_type": "registration",
                "created_at": datetime.now().isoformat()
            }
            
            # Add success status if needed, or just track the event
            # Based on schema error, let's keep it minimal to ensure it works
            # If 'success' column exists, we can add it, but let's stick to core fields
            # The error was about 'method', so removing that is the priority.
            # Let's also remove 'success' to be safe unless we know it exists, 
            # but usually event_type is enough for counting.
            # However, looking at other methods, they use specific fields.
            # Let's try to keep it simple.
            
            self.supabase.table('analytics_events').insert(data).execute()
            logger.debug(f"✓ Tracked registration for {user_id}")
            
        except Exception as e:
            logger.error(f"Failed to track registration: {e}")
    
    async def track_error(
        self, 
        user_id: str,
        error_type: str, 
        error_message: str,
        stack_trace: str = None
    ):
        """บันทึก error"""
        try:
            data = {
                "user_id": user_id,
                "event_type": "error",
                "error_type": error_type,
                "error_message": error_message[:500],
                "stack_trace": stack_trace[:1000] if stack_trace else None,
                "created_at": datetime.now().isoformat()
            }
            
            self.supabase.table('analytics_events').insert(data).execute()
            logger.debug(f"✓ Tracked error: {error_type}")
            
        except Exception as e:
            logger.error(f"Failed to track error: {e}")
    
    async def get_dashboard_stats(self, days: int = 1) -> dict:
        """ดึงสถิติสำหรับ dashboard"""
        try:
            # Calculate date range
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)
            
            # Get all events in date range
            result = self.supabase.table('analytics_events')\
                .select('*')\
                .gte('created_at', start_date.isoformat())\
                .lte('created_at', end_date.isoformat())\
                .execute()
            
            events = result.data if result.data else []
            
            # Calculate statistics
            unique_users = set()
            image_count = 0
            question_count = 0
            error_count = 0
            disease_counter = {}
            pest_type_counter = {
                "เชื้อรา": 0,
                "แมลง": 0,
                "วัชพืช": 0
            }
            product_counter = {}
            response_times = []
            error_types = {}
            daily_activity = {}
            # Additional per-day metrics
            daily_users_sets = {}
            daily_response_times_by_day = {}
            daily_requests_by_day = {}
            daily_errors_by_day = {}
            
            for event in events:
                user_id = event.get('user_id')
                event_type = event.get('event_type')
                
                if user_id:
                    unique_users.add(user_id)
                
                # Track by event type
                if event_type == 'image_analysis':
                    image_count += 1
                    disease = event.get('disease_name')
                    if disease:
                        disease_counter[disease] = disease_counter.get(disease, 0) + 1
                    
                    pest_type = event.get('pest_type')
                    if pest_type:
                        # Normalize pest type if needed, or just count
                        if pest_type in pest_type_counter:
                            pest_type_counter[pest_type] += 1
                        else:
                            pest_type_counter[pest_type] = pest_type_counter.get(pest_type, 0) + 1
                    
                    response_time = event.get('response_time_ms', 0)
                    if response_time:
                        response_times.append(response_time)
                
                elif event_type == 'question':
                    question_count += 1
                    response_time = event.get('response_time_ms', 0)
                    if response_time:
                        response_times.append(response_time)
                
                elif event_type == 'product_recommendation':
                    product = event.get('product_name')
                    if product:
                        product_counter[product] = product_counter.get(product, 0) + 1
                
                elif event_type == 'error':
                    error_count += 1
                    error_type = event.get('error_type', 'unknown')
                    error_types[error_type] = error_types.get(error_type, 0) + 1
                
                # Track daily activity and per-day aggregates
                created_at = event.get('created_at')
                if created_at:
                    try:
                        # Parse date (YYYY-MM-DD)
                        date_str = datetime.fromisoformat(created_at).strftime('%Y-%m-%d')
                        # total events per day
                        daily_activity[date_str] = daily_activity.get(date_str, 0) + 1

                        # unique users per day
                        if user_id:
                            if date_str not in daily_users_sets:
                                daily_users_sets[date_str] = set()
                            daily_users_sets[date_str].add(user_id)

                        # requests (image_analysis + question) per day
                        if event_type in ('image_analysis', 'question'):
                            daily_requests_by_day[date_str] = daily_requests_by_day.get(date_str, 0) + 1

                        # response times per day
                        response_time = event.get('response_time_ms', 0)
                        if response_time and event_type in ('image_analysis', 'question'):
                            if date_str not in daily_response_times_by_day:
                                daily_response_times_by_day[date_str] = []
                            daily_response_times_by_day[date_str].append(response_time)

                        # errors per day
                        if event_type == 'error':
                            daily_errors_by_day[date_str] = daily_errors_by_day.get(date_str, 0) + 1

                    except:
                        pass
            
            # Calculate averages
            avg_response_time = sum(response_times) / len(response_times) if response_times else 0
            total_requests = image_count + question_count
            error_rate = (error_count / total_requests * 100) if total_requests > 0 else 0
            
            # Sort and get top items
            top_diseases = sorted(disease_counter.items(), key=lambda x: x[1], reverse=True)[:10]
            top_products = sorted(product_counter.items(), key=lambda x: x[1], reverse=True)[:10]
            # Ensure specific order for pest types
            # User wants: เชื้อรา, แมลง, วัชพืช
            priority_types = ["เชื้อรา", "แมลง", "วัชพืช"]
            top_pest_types = []
            for pt in priority_types:
                if pt in pest_type_counter:
                    top_pest_types.append((pt, pest_type_counter[pt]))
            # Add others if any
            for pt, count in pest_type_counter.items():
                if pt not in priority_types:
                    top_pest_types.append((pt, count))
            
            top_errors = sorted(error_types.items(), key=lambda x: x[1], reverse=True)[:5]
            
            # Determine health status
            health_status = "healthy"
            if error_rate > 20 or avg_response_time > 10000:
                health_status = "unhealthy"
            elif error_rate > 10 or avg_response_time > 5000:
                health_status = "degraded"

            # Get user statistics (provinces)
            users_result = self.supabase.table('users').select('province').execute()
            users_data = users_result.data if users_result.data else []
            
            province_counter = {}
            for user in users_data:
                province = user.get('province')
                if province:
                    province_counter[province] = province_counter.get(province, 0) + 1
            
            top_provinces = sorted(province_counter.items(), key=lambda x: x[1], reverse=True)[:5]

            # Prepare daily series: avg response time and error rate per day
            daily_response_time_avg = {}
            for d, times in daily_response_times_by_day.items():
                daily_response_time_avg[d] = round(sum(times) / len(times), 2) if times else 0

            daily_error_rate_percent = {}
            for d, err_count in daily_errors_by_day.items():
                reqs = daily_requests_by_day.get(d, 0)
                daily_error_rate_percent[d] = round((err_count / reqs * 100) if reqs > 0 else 0, 2)

            # daily unique users
            daily_unique_users = {d: len(s) for d, s in daily_users_sets.items()}

            return {
                "overview": {
                    "unique_users": len(unique_users),
                    "images_analyzed": image_count,
                    "questions_asked": question_count,
                    "total_requests": total_requests,
                    "errors": error_count
                },
                "performance": {
                    "avg_response_time_ms": round(avg_response_time, 2),
                    "error_rate_percent": round(error_rate, 2)
                },
                "health": {
                    "status": health_status
                },
                "top_diseases": [
                    {"name": name, "count": count} 
                    for name, count in top_diseases
                ],
                "top_products": [
                    {"name": name, "count": count} 
                    for name, count in top_products
                ],
                "pest_types": [
                    {"type": ptype, "count": count} 
                    for ptype, count in top_pest_types
                ],
                "top_provinces": [
                    {"name": name, "count": count} 
                    for name, count in top_provinces
                ],
                "top_errors": [
                    {"type": etype, "count": count} 
                    for etype, count in top_errors
                ],
                "daily_activity": dict(sorted(daily_activity.items())),
                "daily_requests": dict(sorted(daily_requests_by_day.items())),
                "daily_users": dict(sorted(daily_unique_users.items())),
                "daily_response_time": dict(sorted(daily_response_time_avg.items())),
                "daily_error_rate": dict(sorted(daily_error_rate_percent.items())),
                "date_range": {
                    "start": start_date.isoformat(),
                    "end": end_date.isoformat(),
                    "days": days
                }
            }
            
        except Exception as e:
            logger.error(f"Failed to get dashboard stats: {e}")
            return {
                "overview": {
                    "unique_users": 0,
                    "images_analyzed": 0,
                    "questions_asked": 0,
                    "total_requests": 0,
                    "errors": 0
                },
                "performance": {
                    "avg_response_time_ms": 0,
                    "error_rate_percent": 0
                },
                "top_diseases": [],
                "top_products": [],
                "pest_types": [],
                "top_errors": [],
                "hourly_activity": {},
                "error": str(e)
            }
    
    async def get_health_status(self) -> dict:
        """ตรวจสอบสุขภาพของระบบ"""
        try:
            # Get stats for last hour
            stats = await self.get_dashboard_stats(days=1)
            
            error_rate = stats["performance"]["error_rate_percent"]
            avg_response_time = stats["performance"]["avg_response_time_ms"]
            
            # Determine health status
            status = "healthy"
            warnings = []
            
            # Check error rate
            if error_rate > 10:
                status = "degraded"
                warnings.append(f"High error rate: {error_rate:.1f}%")
            elif error_rate > 20:
                status = "unhealthy"
                warnings.append(f"Critical error rate: {error_rate:.1f}%")
            
            # Check response time
            if avg_response_time > 5000:  # 5 seconds
                if status == "healthy":
                    status = "degraded"
                warnings.append(f"Slow response time: {avg_response_time:.0f}ms")
            elif avg_response_time > 10000:  # 10 seconds
                status = "unhealthy"
                warnings.append(f"Critical response time: {avg_response_time:.0f}ms")
            
            return {
                "status": status,
                "error_rate": round(error_rate, 2),
                "avg_response_time_ms": round(avg_response_time, 2),
                "warnings": warnings,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to get health status: {e}")
            return {
                "status": "unknown",
                "error_rate": 0,
                "avg_response_time_ms": 0,
                "warnings": [f"Failed to check health: {str(e)}"],
                "timestamp": datetime.now().isoformat()
            }

# ============================================================================#
# Alert System
# ============================================================================#

class AlertManager:
    """
    ระบบแจ้งเตือนด้วย Supabase
    บันทึก alert ลง database
    """
    
    def __init__(self, supabase_client: Client):
        self.supabase = supabase_client
        self.alert_thresholds = {
            "error_rate": 15.0,  # แจ้งเตือนถ้า error rate > 15%
            "response_time": 8000,  # แจ้งเตือนถ้า response time > 8 วินาที
            "daily_errors": 50  # แจ้งเตือนถ้า error > 50 ครั้ง/วัน
        }
        logger.info("✓ Alert manager initialized (Supabase)")
    
    async def check_and_alert(self, analytics_tracker: AnalyticsTracker):
        """ตรวจสอบและสร้าง alert ถ้าจำเป็น"""
        try:
            health = await analytics_tracker.get_health_status()
            
            # Check error rate
            if health["error_rate"] > self.alert_thresholds["error_rate"]:
                await self._create_alert(
                    "high_error_rate",
                    f"Error rate is {health['error_rate']:.1f}% (threshold: {self.alert_thresholds['error_rate']}%)",
                    "warning" if health["error_rate"] < 20 else "critical"
                )
            
            # Check response time
            if health["avg_response_time_ms"] > self.alert_thresholds["response_time"]:
                await self._create_alert(
                    "slow_response",
                    f"Average response time is {health['avg_response_time_ms']:.0f}ms (threshold: {self.alert_thresholds['response_time']}ms)",
                    "warning" if health["avg_response_time_ms"] < 10000 else "critical"
                )
            
        except Exception as e:
            logger.error(f"Failed to check and alert: {e}")
    
    async def _create_alert(self, alert_type: str, message: str, severity: str):
        """สร้าง alert"""
        try:
            alert = {
                "alert_type": alert_type,
                "message": message,
                "severity": severity,
                "created_at": datetime.now().isoformat()
            }
            
            # Log alert
            if severity == "critical":
                logger.error(f"🚨 ALERT: {message}")
            else:
                logger.warning(f"⚠️ ALERT: {message}")
            
            # Store in database
            self.supabase.table('analytics_alerts').insert(alert).execute()
            
        except Exception as e:
            logger.error(f"Failed to create alert: {e}")
    
    async def get_active_alerts(self) -> List[dict]:
        """ดึง alert ที่ยังไม่หมดอายุ (ภายใน 1 ชั่วโมง)"""
        try:
            cutoff_time = datetime.now() - timedelta(hours=1)
            
            result = self.supabase.table('analytics_alerts')\
                .select('*')\
                .gte('created_at', cutoff_time.isoformat())\
                .order('created_at', desc=True)\
                .execute()
            
            return result.data if result.data else []
            
        except Exception as e:
            logger.error(f"Failed to get active alerts: {e}")
            return []
