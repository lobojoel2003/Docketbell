from django.urls import path

from docketbell.sms import views

app_name = "sms"

urlpatterns = [
    path("twilio/inbound/", views.twilio_inbound, name="twilio-inbound"),
    path("twilio/status/", views.twilio_status, name="twilio-status"),
    path("gateway/inbound/", views.gateway_inbound, name="gateway-inbound"),
    path("gateway/status/", views.gateway_status, name="gateway-status"),
]
