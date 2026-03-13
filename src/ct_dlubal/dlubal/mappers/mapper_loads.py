class LoadMapper:
    """Standard Lastfälle für Dlubal"""
    def __init__(self, Loc):
        self.Loc = Loc

    # To-Do: Check load case validity!

    def create_load_cases(self, selected_cases=["sw"]):
        """Erzeugt Lastfälle basierend auf der Auswahl des Benutzers."""
        objects = []
        
        # Statische Analyseeinstellungen (Linear)
        analysis_settings = self.Loc.StaticAnalysisSettings(no=1, name="Linear Analysis", analysis_type=0)
        objects.append(analysis_settings)

        # Lastfall 1: Eigengewicht
        if "sw" in selected_cases:
            objects.append(self.Loc.LoadCase(
                no=1, 
                name="Self-Weight", 
                action_category=11, # ACTION_CATEGORY_PERMANENT_G
                analysis_type=1,
                self_weight_active=True,
                self_weight_factor_z=1.0,
                static_analysis_settings=1
            ))

        # Lastfall 2: Nutzlast / Live Load (Beispiel)
        if "live" in selected_cases:
            objects.append(self.Loc.LoadCase(
                no=2,
                name="Live Load",
                action_category=20, # ACTION_CATEGORY_IMPOSED_LOADS_CATEGORY_A_DOMESTIC_RESIDENTIAL_AREAS_QI_A
                analysis_type=1,
                static_analysis_settings=1
            ))

        # Lastfall 3: Schnee (Beispiel)
        if "snow" in selected_cases:
            objects.append(self.Loc.LoadCase(
                no=3,
                name="Snow Load",
                action_category=40, # ACTION_CATEGORY_SNOW_ICE_LOADS_H_LESS_OR_EQUAL_TO_1000_M_QS
                analysis_type=1,
                static_analysis_settings=1
            ))

        return objects

    def default_load_case(self):
        return self.create_load_cases(["sw"])
