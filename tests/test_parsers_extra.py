"""Tests for Ruby parser and SwiftUI flow detection."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from analyzer.models import Component
from analyzer.parsers.ruby import RubyParser
from analyzer.swiftui_flow import SwiftUIFlowDetector

# ===========================================================================
# Fixtures
# ===========================================================================


@pytest.fixture
def ruby():
    return RubyParser()


@pytest.fixture
def detector():
    return SwiftUIFlowDetector()


# ===========================================================================
# Ruby Parser: extract_symbols
# ===========================================================================


class TestRubyExtractSymbols:
    """Tests for RubyParser.extract_symbols."""

    def test_class_definition(self, ruby):
        content = "class User\n  def name; end\nend\n"
        symbols = ruby.extract_symbols(content, "app/models/user.rb")
        classes = [s for s in symbols if s.kind == "class"]
        assert len(classes) == 1
        assert classes[0].name == "User"
        assert classes[0].visibility == "public"
        assert classes[0].line == 1

    def test_module_definition(self, ruby):
        content = "module Authentication\n  def login; end\nend\n"
        symbols = ruby.extract_symbols(content, "lib/auth.rb")
        modules = [s for s in symbols if s.kind == "module"]
        assert len(modules) == 1
        assert modules[0].name == "Authentication"

    def test_nested_module_with_scope_operator(self, ruby):
        content = "class Admin::UsersController\n  def index; end\nend\n"
        symbols = ruby.extract_symbols(content, "app/controllers/admin/users_controller.rb")
        classes = [s for s in symbols if s.kind == "class"]
        assert len(classes) == 1
        assert classes[0].name == "Admin::UsersController"

    def test_deeply_nested_module(self, ruby):
        content = "module Api::V2::Internal\n  def ping; end\nend\n"
        symbols = ruby.extract_symbols(content, "lib/api.rb")
        modules = [s for s in symbols if s.kind == "module"]
        assert len(modules) == 1
        assert modules[0].name == "Api::V2::Internal"

    def test_instance_method(self, ruby):
        content = "class Foo\n  def bar\n    42\n  end\nend\n"
        symbols = ruby.extract_symbols(content, "foo.rb")
        methods = [s for s in symbols if s.kind == "function"]
        assert len(methods) == 1
        assert methods[0].name == "bar"
        assert methods[0].visibility == "public"

    def test_class_method_self_dot(self, ruby):
        content = "class Foo\n  def self.create\n    new\n  end\nend\n"
        symbols = ruby.extract_symbols(content, "foo.rb")
        methods = [s for s in symbols if s.kind == "function"]
        assert len(methods) == 1
        assert methods[0].name == "self.create"

    def test_predicate_method_question_mark(self, ruby):
        content = "class Foo\n  def valid?\n    true\n  end\nend\n"
        symbols = ruby.extract_symbols(content, "foo.rb")
        methods = [s for s in symbols if s.kind == "function"]
        assert len(methods) == 1
        assert methods[0].name == "valid?"

    def test_bang_method_exclamation(self, ruby):
        content = "class Foo\n  def save!\n    true\n  end\nend\n"
        symbols = ruby.extract_symbols(content, "foo.rb")
        methods = [s for s in symbols if s.kind == "function"]
        assert len(methods) == 1
        assert methods[0].name == "save!"

    def test_assignment_method_equals(self, ruby):
        content = "class Foo\n  def name=(val)\n    @name = val\n  end\nend\n"
        symbols = ruby.extract_symbols(content, "foo.rb")
        methods = [s for s in symbols if s.kind == "function"]
        assert len(methods) == 1
        assert methods[0].name == "name="

    def test_private_method_underscore_prefix(self, ruby):
        content = "class Foo\n  def _internal_setup\n    nil\n  end\nend\n"
        symbols = ruby.extract_symbols(content, "foo.rb")
        methods = [s for s in symbols if s.kind == "function"]
        assert len(methods) == 1
        assert methods[0].name == "_internal_setup"
        assert methods[0].visibility == "private"

    def test_self_class_method_not_private(self, ruby):
        """self.methods should be public even if the bare name would not start with _."""
        content = "class Foo\n  def self.build\n    new\n  end\nend\n"
        symbols = ruby.extract_symbols(content, "foo.rb")
        methods = [s for s in symbols if s.kind == "function"]
        assert methods[0].name == "self.build"
        assert methods[0].visibility == "public"

    def test_multiple_symbols(self, ruby):
        content = (
            "module Helpers\n"
            "  class Formatter\n"
            "    def format\n"
            "      nil\n"
            "    end\n"
            "    def self.parse\n"
            "      nil\n"
            "    end\n"
            "  end\n"
            "end\n"
        )
        symbols = ruby.extract_symbols(content, "helpers.rb")
        names = [s.name for s in symbols]
        assert "Helpers" in names
        assert "Formatter" in names
        assert "format" in names
        assert "self.parse" in names

    def test_end_line_tracking(self, ruby):
        content = (
            "def simple\n"
            "  1\n"
            "end\n"
        )
        symbols = ruby.extract_symbols(content, "t.rb")
        assert len(symbols) == 1
        assert symbols[0].line == 1
        assert symbols[0].end_line == 3

    def test_docstring_extraction(self, ruby):
        content = (
            "# This sets up the connection.\n"
            "def connect\n"
            "  nil\n"
            "end\n"
        )
        symbols = ruby.extract_symbols(content, "t.rb")
        assert symbols[0].docstring is not None
        assert "connection" in symbols[0].docstring


# ===========================================================================
# Ruby Parser: extract_imports
# ===========================================================================


class TestRubyExtractImports:
    """Tests for RubyParser.extract_imports."""

    def test_require_single_quotes(self, ruby):
        content = "require 'json'\nrequire 'net/http'\n"
        imports = ruby.extract_imports(content)
        assert "json" in imports
        assert "net" in imports  # split on /

    def test_require_double_quotes(self, ruby):
        content = 'require "yaml"\n'
        imports = ruby.extract_imports(content)
        assert "yaml" in imports

    def test_require_relative(self, ruby):
        content = "require_relative 'lib/helpers'\n"
        imports = ruby.extract_imports(content)
        assert "lib" in imports

    def test_mixed_imports_deduped(self, ruby):
        content = (
            "require 'json'\n"
            "require 'json'\n"
            "require_relative 'json/parser'\n"
        )
        imports = ruby.extract_imports(content)
        assert imports.count("json") == 1

    def test_no_imports(self, ruby):
        content = "class Foo\nend\n"
        imports = ruby.extract_imports(content)
        assert imports == []


# ===========================================================================
# Ruby Parser: detect_framework
# ===========================================================================


class TestRubyDetectFramework:
    """Tests for RubyParser.detect_framework."""

    def test_rails_by_rails_keyword(self, ruby):
        content = "class App < Rails::Application\nend\n"
        assert ruby.detect_framework(content) == "Rails"

    def test_rails_by_active_record(self, ruby):
        content = "class User < ActiveRecord::Base\nend\n"
        assert ruby.detect_framework(content) == "Rails"

    def test_rails_by_action_controller(self, ruby):
        content = "class UsersController < ActionController::Base\nend\n"
        assert ruby.detect_framework(content) == "Rails"

    def test_sinatra(self, ruby):
        """detect_framework checks for 'Sinatra' (capitalized) in content."""
        content = "require 'sinatra'\nclass App < Sinatra::Base\nend\n"
        assert ruby.detect_framework(content) == "Sinatra"

    def test_sinatra_base(self, ruby):
        content = "class App < Sinatra::Base\nend\n"
        assert ruby.detect_framework(content) == "Sinatra"

    def test_grape(self, ruby):
        content = "class API < Grape::API\nend\n"
        assert ruby.detect_framework(content) == "Grape"

    def test_hanami(self, ruby):
        """detect_framework checks for 'Hanami' (capitalized) in content."""
        content = "require 'hanami'\nmodule Hanami::App\nend\n"
        assert ruby.detect_framework(content) == "Hanami"

    def test_no_framework(self, ruby):
        content = "class PlainRuby\n  def run; end\nend\n"
        assert ruby.detect_framework(content) is None

    def test_rails_takes_priority_over_sinatra(self, ruby):
        """Rails check comes first, so mixed content returns Rails."""
        content = "require 'sinatra'\nclass User < ActiveRecord::Base\nend\n"
        assert ruby.detect_framework(content) == "Rails"


# ===========================================================================
# Ruby Parser: detect_api_endpoints
# ===========================================================================


class TestRubyDetectApiEndpoints:
    """Tests for RubyParser.detect_api_endpoints."""

    def test_rails_get_route(self, ruby):
        content = "get '/users'\n"
        endpoints = ruby.detect_api_endpoints(content)
        paths = [e["path"] for e in endpoints]
        assert "/users" in paths

    def test_rails_post_route(self, ruby):
        content = "post '/users'\n"
        endpoints = ruby.detect_api_endpoints(content)
        methods = [e["method"] for e in endpoints]
        assert "POST" in methods

    def test_rails_delete_route(self, ruby):
        content = "delete '/users/:id'\n"
        endpoints = ruby.detect_api_endpoints(content)
        methods = [e["method"] for e in endpoints]
        assert "DELETE" in methods

    def test_sinatra_style_routes(self, ruby):
        content = (
            "get '/hello' do\n"
            "  'Hello'\n"
            "end\n"
            "post '/data' do\n"
            "  'OK'\n"
            "end\n"
        )
        endpoints = ruby.detect_api_endpoints(content)
        paths = [e["path"] for e in endpoints]
        assert "/hello" in paths
        assert "/data" in paths

    def test_put_and_patch_routes(self, ruby):
        content = "put '/items/:id'\npatch '/items/:id'\n"
        endpoints = ruby.detect_api_endpoints(content)
        methods = [e["method"] for e in endpoints]
        assert "PUT" in methods
        assert "PATCH" in methods

    def test_no_endpoints(self, ruby):
        content = "class Foo\n  def bar; end\nend\n"
        endpoints = ruby.detect_api_endpoints(content)
        assert endpoints == []


# ===========================================================================
# Ruby Parser: _find_ruby_end
# ===========================================================================


class TestRubyFindEnd:
    """Tests for RubyParser._find_ruby_end."""

    def test_simple_method(self, ruby):
        lines = ["def foo", "  1", "end"]
        assert ruby._find_ruby_end(lines, 0) == 2

    def test_nested_if(self, ruby):
        lines = [
            "def foo",
            "  if bar",
            "    baz",
            "  end",
            "end",
        ]
        assert ruby._find_ruby_end(lines, 0) == 4

    def test_nested_class_in_module(self, ruby):
        lines = [
            "module Outer",
            "  class Inner",
            "    def go",
            "      1",
            "    end",
            "  end",
            "end",
        ]
        assert ruby._find_ruby_end(lines, 0) == 6

    def test_do_block(self, ruby):
        """A line ending with ' do' (no trailing args) increments depth."""
        lines = [
            "def each",
            "  items.each do",
            "    yield",
            "  end",
            "end",
        ]
        assert ruby._find_ruby_end(lines, 0) == 4

    def test_do_block_with_params_does_not_nest(self, ruby):
        """'do |i|' does not end with ' do', so depth stays at 1."""
        lines = [
            "def each",
            "  items.each do |i|",
            "    yield i",
            "  end",
            "end",
        ]
        # The first 'end' closes the def because 'do |i|' is not detected
        assert ruby._find_ruby_end(lines, 0) == 3

    def test_no_matching_end_returns_fallback(self, ruby):
        """When no matching end is found within 500 lines, returns start+10."""
        lines = ["def broken"] + ["  stuff"] * 5
        result = ruby._find_ruby_end(lines, 0)
        # Should return min(start + 10, len(lines) - 1) = min(10, 5) = 5
        assert result == 5


# ===========================================================================
# SwiftUI Flow Detector: _extract_view_body
# ===========================================================================


class TestSwiftUIExtractViewBody:
    """Tests for SwiftUIFlowDetector._extract_view_body."""

    def test_extracts_specific_view(self, detector):
        content = (
            "struct HomeView: View {\n"
            "    var body: some View {\n"
            "        Text(\"Home\")\n"
            "    }\n"
            "}\n"
            "\n"
            "struct SettingsView: View {\n"
            "    var body: some View {\n"
            "        Text(\"Settings\")\n"
            "    }\n"
            "}\n"
        )
        body = detector._extract_view_body(content, "HomeView")
        assert "Home" in body
        # SettingsView should not be included in the HomeView body
        assert "Settings" not in body

    def test_fallback_full_content_when_struct_not_found(self, detector):
        content = "struct SomeOtherStruct {\n    var x: Int\n}\n"
        body = detector._extract_view_body(content, "MissingView")
        # Falls back to entire content
        assert body == content


# ===========================================================================
# SwiftUI Flow Detector: _detect_tabs
# ===========================================================================


class TestSwiftUIDetectTabs:
    """Tests for SwiftUIFlowDetector._detect_tabs."""

    def test_tabview_with_multiple_tabs(self, detector):
        content = (
            "TabView {\n"
            "    HomeView()\n"
            "        .tabItem {\n"
            "            Label(\"Home\", systemImage: \"house\")\n"
            "        }\n"
            "    SettingsView()\n"
            "        .tabItem {\n"
            "            Label(\"Settings\", systemImage: \"gear\")\n"
            "        }\n"
            "}\n"
        )
        tabs = detector._detect_tabs(content)
        assert len(tabs) == 2
        assert tabs[0]["label"] == "Home"
        assert tabs[0]["view_name"] == "HomeView"
        assert tabs[1]["label"] == "Settings"
        assert tabs[1]["view_name"] == "SettingsView"

    def test_no_tabview_returns_empty(self, detector):
        content = "VStack {\n    Text(\"Hello\")\n}\n"
        tabs = detector._detect_tabs(content)
        assert tabs == []

    def test_tabview_with_content_suffix(self, detector):
        """Views ending in Content should be matched."""
        content = (
            "TabView {\n"
            "    SessionTabContent()\n"
            "        .tabItem {\n"
            "            Label(\"Session\", systemImage: \"brain\")\n"
            "        }\n"
            "}\n"
        )
        tabs = detector._detect_tabs(content)
        assert len(tabs) == 1
        assert tabs[0]["view_name"] == "SessionTabContent"


# ===========================================================================
# SwiftUI Flow Detector: _detect_navigation_targets
# ===========================================================================


class TestSwiftUIDetectNavigationTargets:
    """Tests for SwiftUIFlowDetector._detect_navigation_targets."""

    def test_navigation_link_content_closure(self, detector):
        content = (
            "NavigationLink {\n"
            "    DetailView(item: item)\n"
            "} label: {\n"
            "    Text(item.name)\n"
            "}\n"
        )
        targets = detector._detect_navigation_targets(content)
        assert len(targets) == 1
        assert targets[0]["target"] == "DetailView"
        assert targets[0]["nav_type"] == "push"

    def test_navigation_link_destination_parameter(self, detector):
        content = 'NavigationLink(destination: ProfileView(user: u)) {\n    Text("Profile")\n}\n'
        targets = detector._detect_navigation_targets(content)
        assert len(targets) == 1
        assert targets[0]["target"] == "ProfileView"

    def test_navigation_destination_modifier(self, detector):
        content = (
            ".navigationDestination(isPresented: $show) {\n"
            "    ItemDetailView(item: selected)\n"
            "}\n"
        )
        targets = detector._detect_navigation_targets(content)
        assert len(targets) == 1
        assert targets[0]["target"] == "ItemDetailView"

    def test_deduplicates_targets(self, detector):
        content = (
            "NavigationLink {\n"
            "    DetailView(item: a)\n"
            "} label: { Text(\"A\") }\n"
            "NavigationLink {\n"
            "    DetailView(item: b)\n"
            "} label: { Text(\"B\") }\n"
        )
        targets = detector._detect_navigation_targets(content)
        assert len(targets) == 1
        assert targets[0]["target"] == "DetailView"

    def test_no_navigation_targets(self, detector):
        content = "VStack { Text(\"Hello\") }\n"
        targets = detector._detect_navigation_targets(content)
        assert targets == []


# ===========================================================================
# SwiftUI Flow Detector: _detect_modal_targets
# ===========================================================================


class TestSwiftUIDetectModalTargets:
    """Tests for SwiftUIFlowDetector._detect_modal_targets."""

    def test_sheet_target(self, detector):
        content = (
            ".sheet(isPresented: $showAdd) {\n"
            "    AddItemView(onSave: save)\n"
            "}\n"
        )
        targets = detector._detect_modal_targets(content)
        assert len(targets) == 1
        assert targets[0]["target"] == "AddItemView"
        assert targets[0]["nav_type"] == "sheet"

    def test_fullscreen_cover_target(self, detector):
        content = (
            ".fullScreenCover(isPresented: $showOnboarding) {\n"
            "    OnboardingView()\n"
            "}\n"
        )
        targets = detector._detect_modal_targets(content)
        assert len(targets) == 1
        assert targets[0]["target"] == "OnboardingView"
        assert targets[0]["nav_type"] == "fullscreen"

    def test_both_sheet_and_fullscreen(self, detector):
        content = (
            ".sheet(isPresented: $a) {\n"
            "    EditView()\n"
            "}\n"
            ".fullScreenCover(isPresented: $b) {\n"
            "    PreviewScreen()\n"
            "}\n"
        )
        targets = detector._detect_modal_targets(content)
        names = {t["target"] for t in targets}
        assert "EditView" in names
        assert "PreviewScreen" in names

    def test_no_modal_targets(self, detector):
        content = "Text(\"Nothing here\")\n"
        targets = detector._detect_modal_targets(content)
        assert targets == []


# ===========================================================================
# SwiftUI Flow Detector: _detect_embedded_views
# ===========================================================================


class TestSwiftUIDetectEmbeddedViews:
    """Tests for SwiftUIFlowDetector._detect_embedded_views."""

    def test_finds_known_views(self, detector):
        content = "VStack {\n    ProfileView(user: u)\n    StatsView()\n}\n"
        view_map = {"ProfileView": "a.swift", "StatsView": "b.swift"}
        targets = detector._detect_embedded_views(content, "ParentView", view_map)
        names = {t["target"] for t in targets}
        assert "ProfileView" in names
        assert "StatsView" in names
        assert all(t["nav_type"] == "embeds" for t in targets)

    def test_skips_source_view_name(self, detector):
        content = "VStack {\n    SelfView()\n}\n"
        view_map = {"SelfView": "a.swift"}
        targets = detector._detect_embedded_views(content, "SelfView", view_map)
        assert len(targets) == 0

    def test_skips_unknown_views(self, detector):
        content = "VStack {\n    UnknownThing()\n}\n"
        view_map = {"KnownView": "a.swift"}
        targets = detector._detect_embedded_views(content, "Parent", view_map)
        assert len(targets) == 0

    def test_deduplicates_embedded(self, detector):
        content = "VStack {\n    ChildView(a: 1)\n    ChildView(b: 2)\n}\n"
        view_map = {"ChildView": "c.swift"}
        targets = detector._detect_embedded_views(content, "Parent", view_map)
        assert len(targets) == 1


# ===========================================================================
# SwiftUI Flow Detector: _is_ui_directory
# ===========================================================================


class TestSwiftUIIsUIDirectory:
    """Tests for SwiftUIFlowDetector._is_ui_directory."""

    def test_views_directory(self, detector):
        assert detector._is_ui_directory("App/Views/HomeView.swift") is True

    def test_screens_directory(self, detector):
        assert detector._is_ui_directory("App/Screens/Login.swift") is True

    def test_ui_directory(self, detector):
        assert detector._is_ui_directory("UI/Components/Card.swift") is True

    def test_features_directory(self, detector):
        assert detector._is_ui_directory("Features/Profile/ProfileView.swift") is True

    def test_non_ui_directory(self, detector):
        assert detector._is_ui_directory("Models/User.swift") is False

    def test_source_root_only(self, detector):
        assert detector._is_ui_directory("Sources/App.swift") is False


# ===========================================================================
# SwiftUI Flow Detector: _has_screen_suffix
# ===========================================================================


class TestSwiftUIHasScreenSuffix:
    """Tests for SwiftUIFlowDetector._has_screen_suffix."""

    def test_view_suffix(self, detector):
        assert detector._has_screen_suffix("HomeView") is True

    def test_screen_suffix(self, detector):
        assert detector._has_screen_suffix("LoginScreen") is True

    def test_page_suffix(self, detector):
        assert detector._has_screen_suffix("AboutPage") is True

    def test_tab_suffix(self, detector):
        assert detector._has_screen_suffix("SettingsTab") is True

    def test_panel_suffix(self, detector):
        assert detector._has_screen_suffix("DebugPanel") is True

    def test_dashboard_suffix(self, detector):
        assert detector._has_screen_suffix("KBDashboard") is True

    def test_no_suffix(self, detector):
        assert detector._has_screen_suffix("UserModel") is False

    def test_helper_name(self, detector):
        assert detector._has_screen_suffix("LoadingSpinner") is False


# ===========================================================================
# SwiftUI Flow Detector: _humanize_view_name
# ===========================================================================


class TestSwiftUIHumanizeViewName:
    """Tests for SwiftUIFlowDetector._humanize_view_name."""

    def test_strips_view_suffix_and_splits(self, detector):
        # The regex only splits on lowercase-to-uppercase boundaries,
        # so "KBDashboard" has no split point (KB is all-caps).
        assert detector._humanize_view_name("KBDashboardView") == "KBDashboard"

    def test_strips_screen_suffix(self, detector):
        assert detector._humanize_view_name("LoginScreen") == "Login"

    def test_strips_page_suffix(self, detector):
        assert detector._humanize_view_name("AboutPage") == "About"

    def test_camel_case_split(self, detector):
        assert detector._humanize_view_name("UserProfileView") == "User Profile"

    def test_single_word_no_suffix(self, detector):
        result = detector._humanize_view_name("Dashboard")
        # "Dashboard" does not have a strippable suffix (only View/Screen/Page stripped)
        assert result == "Dashboard"

    def test_just_view_not_stripped(self, detector):
        """Name 'View' alone should not be stripped to empty."""
        result = detector._humanize_view_name("View")
        assert result == "View"


# ===========================================================================
# SwiftUI Flow Detector: _feature_group_name
# ===========================================================================


class TestSwiftUIFeatureGroupName:
    """Tests for SwiftUIFlowDetector._feature_group_name."""

    def test_ui_subdirectory(self, detector):
        result = detector._feature_group_name("UI/Settings/SettingsView.swift")
        assert result == "Settings"

    def test_views_subdirectory(self, detector):
        result = detector._feature_group_name("Views/Profile/ProfileView.swift")
        assert result == "Profile"

    def test_screens_subdirectory(self, detector):
        result = detector._feature_group_name("Screens/Onboarding/WelcomeView.swift")
        assert result == "Onboarding"

    def test_fallback_to_parent_directory(self, detector):
        result = detector._feature_group_name("MyApp/Login/LoginView.swift")
        assert result == "Login"

    def test_file_at_root(self, detector):
        """A file with no meaningful parent returns None."""
        result = detector._feature_group_name("AppView.swift")
        # parent name is "" so returns None
        assert result is None


# ===========================================================================
# SwiftUI Flow Detector: detect (integration)
# ===========================================================================


class TestSwiftUIDetectIntegration:
    """Integration tests for SwiftUIFlowDetector.detect."""

    def test_full_tabview_with_screens_and_navigation(self, detector, tmp_path):
        """Full pipeline: TabView with tabs, navigation, and sheets."""
        # Create the main app file with TabView
        app_swift = (
            "import SwiftUI\n"
            "\n"
            "@main\n"
            "struct MyApp: App {\n"
            "    var body: some Scene {\n"
            "        WindowGroup {\n"
            "            ContentView()\n"
            "        }\n"
            "    }\n"
            "}\n"
            "\n"
            "struct ContentView: View {\n"
            "    var body: some View {\n"
            "        TabView {\n"
            "            HomeView()\n"
            "                .tabItem {\n"
            "                    Label(\"Home\", systemImage: \"house\")\n"
            "                }\n"
            "            SettingsView()\n"
            "                .tabItem {\n"
            "                    Label(\"Settings\", systemImage: \"gear\")\n"
            "                }\n"
            "        }\n"
            "    }\n"
            "}\n"
        )
        (tmp_path / "MyApp.swift").write_text(app_swift)

        # Create HomeView with NavigationLink
        views_dir = tmp_path / "Views"
        views_dir.mkdir()
        home_swift = (
            "import SwiftUI\n"
            "\n"
            "struct HomeView: View {\n"
            "    var body: some View {\n"
            "        NavigationStack {\n"
            "            List {\n"
            "                NavigationLink {\n"
            "                    DetailView(item: item)\n"
            "                } label: {\n"
            "                    Text(\"Detail\")\n"
            "                }\n"
            "            }\n"
            "        }\n"
            "    }\n"
            "}\n"
        )
        (views_dir / "HomeView.swift").write_text(home_swift)

        # Create SettingsView with sheet
        settings_swift = (
            "import SwiftUI\n"
            "\n"
            "struct SettingsView: View {\n"
            "    @State private var showProfile = false\n"
            "    var body: some View {\n"
            "        Text(\"Settings\")\n"
            "            .sheet(isPresented: $showProfile) {\n"
            "                ProfileView()\n"
            "            }\n"
            "    }\n"
            "}\n"
        )
        (views_dir / "SettingsView.swift").write_text(settings_swift)

        # Create DetailView
        detail_swift = (
            "import SwiftUI\n"
            "\n"
            "struct DetailView: View {\n"
            "    var body: some View {\n"
            "        Text(\"Detail\")\n"
            "    }\n"
            "}\n"
        )
        (views_dir / "DetailView.swift").write_text(detail_swift)

        # Create ProfileView
        profile_swift = (
            "import SwiftUI\n"
            "\n"
            "struct ProfileView: View {\n"
            "    var body: some View {\n"
            "        Text(\"Profile\")\n"
            "    }\n"
            "}\n"
        )
        (views_dir / "ProfileView.swift").write_text(profile_swift)

        # Build a Component with all the files
        component = Component(
            id="my-app",
            name="MyApp",
            type="application",
            path=".",
            language="swift",
            framework="SwiftUI",
            files=[
                "MyApp.swift",
                "Views/HomeView.swift",
                "Views/SettingsView.swift",
                "Views/DetailView.swift",
                "Views/ProfileView.swift",
            ],
        )

        components, relationships = detector.detect(component, tmp_path)

        # Should have a tab container
        tab_containers = [c for c in components if c.type == "tab-container"]
        assert len(tab_containers) == 1

        # Should have tabs
        tab_comps = [c for c in components if c.type == "tab"]
        assert len(tab_comps) == 2
        tab_names = {c.name for c in tab_comps}
        assert "Home" in tab_names
        assert "Settings" in tab_names

        # Should have screen components for Detail and Profile
        screen_comps = [c for c in components if c.type == "screen"]
        screen_names = {c.name for c in screen_comps}
        assert "Detail" in screen_names or "DetailView" in screen_names

        # Should have navigation relationships
        assert len(relationships) > 0
        rel_types = {r.type for r in relationships}
        assert "tab" in rel_types

    def test_no_views_returns_empty(self, detector, tmp_path):
        """When there are no View structs at all, detect returns empty."""
        (tmp_path / "main.swift").write_text(
            "import Foundation\n"
            "print(\"Hello\")\n"
        )
        component = Component(
            id="cli",
            name="CLI",
            type="application",
            path=".",
            language="swift",
            files=["main.swift"],
        )
        components, relationships = detector.detect(component, tmp_path)
        assert components == []
        assert relationships == []

    def test_views_without_tabview(self, detector, tmp_path):
        """Views exist but no TabView entry point and no UI directory classification."""
        (tmp_path / "SomeView.swift").write_text(
            "import SwiftUI\n"
            "struct SomeView: View {\n"
            "    var body: some View { Text(\"hi\") }\n"
            "}\n"
        )
        component = Component(
            id="app",
            name="App",
            type="application",
            path=".",
            language="swift",
            files=["SomeView.swift"],
        )
        components, relationships = detector.detect(component, tmp_path)
        # No tabs, no UI directory, no navigation targets, so it does not classify
        assert components == []
        assert relationships == []

    def test_views_in_ui_directory_classified_as_screens(self, detector, tmp_path):
        """Views in a UI directory with screen suffixes are classified even without tabs."""
        views_dir = tmp_path / "Views"
        views_dir.mkdir()
        (views_dir / "LoginView.swift").write_text(
            "import SwiftUI\n"
            "struct LoginView: View {\n"
            "    var body: some View { Text(\"Login\") }\n"
            "}\n"
        )
        (views_dir / "SignupScreen.swift").write_text(
            "import SwiftUI\n"
            "struct SignupScreen: View {\n"
            "    var body: some View { Text(\"Signup\") }\n"
            "}\n"
        )
        component = Component(
            id="app",
            name="App",
            type="application",
            path=".",
            language="swift",
            files=[
                "Views/LoginView.swift",
                "Views/SignupScreen.swift",
            ],
        )
        components, relationships = detector.detect(component, tmp_path)
        screen_names = {c.name for c in components if c.type == "screen"}
        assert "Login" in screen_names
        assert "Signup" in screen_names

    def test_nonexistent_file_skipped(self, detector, tmp_path):
        """Files that do not exist on disk are silently skipped."""
        component = Component(
            id="app",
            name="App",
            type="application",
            path=".",
            language="swift",
            files=["nonexistent.swift"],
        )
        components, relationships = detector.detect(component, tmp_path)
        assert components == []
        assert relationships == []

    def test_non_swift_files_ignored(self, detector, tmp_path):
        """Non-Swift files are ignored by _collect_view_structs."""
        (tmp_path / "readme.md").write_text("# Hello\n")
        component = Component(
            id="app",
            name="App",
            type="application",
            path=".",
            language="swift",
            files=["readme.md"],
        )
        components, relationships = detector.detect(component, tmp_path)
        assert components == []
        assert relationships == []


# ===========================================================================
# SwiftUI Flow Detector: _collect_view_structs
# ===========================================================================


class TestSwiftUICollectViewStructs:
    """Tests for SwiftUIFlowDetector._collect_view_structs."""

    def test_collects_view_structs(self, detector, tmp_path):
        (tmp_path / "A.swift").write_text(
            "struct AlphaView: View {\n"
            "    var body: some View { Text(\"\") }\n"
            "}\n"
        )
        (tmp_path / "B.swift").write_text(
            "struct BetaView: SomeProtocol, View {\n"
            "    var body: some View { Text(\"\") }\n"
            "}\n"
        )
        view_map = detector._collect_view_structs(
            ["A.swift", "B.swift"], tmp_path
        )
        assert "AlphaView" in view_map
        assert "BetaView" in view_map

    def test_ignores_non_view_structs(self, detector, tmp_path):
        (tmp_path / "C.swift").write_text(
            "struct MyModel: Codable {\n"
            "    var name: String\n"
            "}\n"
        )
        view_map = detector._collect_view_structs(["C.swift"], tmp_path)
        assert len(view_map) == 0
