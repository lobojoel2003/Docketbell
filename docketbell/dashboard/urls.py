from django.urls import path

from docketbell.dashboard import views

app_name = "dashboard"

urlpatterns = [
    path("", views.home, name="home"),
    path("court-dates/", views.court_date_list, name="court-dates"),
    path("court-dates/new/", views.court_date_create, name="court-date-new"),
    path("court-dates/<int:pk>/", views.court_date_detail, name="court-date"),
    path("court-dates/<int:pk>/edit/", views.court_date_edit, name="court-date-edit"),
    path("court-dates/<int:pk>/action/", views.court_date_action, name="court-date-action"),
    path("court-dates/<int:pk>/text/", views.court_date_text, name="court-date-text"),
    path("court-dates/<int:pk>/simulate/", views.court_date_simulate, name="court-date-simulate"),
    path("people/", views.person_list, name="people"),
    path("people/<int:pk>/", views.person_detail, name="person"),
    path("inbox/", views.inbox, name="inbox"),
    path("inbox/<int:pk>/handled/", views.inbox_handle, name="inbox-handle"),
    path("messages/", views.studio, name="studio"),
    path("results/", views.results, name="results"),
    path("import/", views.import_view, name="import"),
    path("import/template.csv", views.import_template, name="import-template"),
]
