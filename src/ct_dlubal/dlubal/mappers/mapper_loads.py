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
                analysis_type=1,
                self_weight_active=True,
                self_weight_factor_z=1.0,
                static_analysis_settings=1
            ))

        # Lastfall 2: Nutzlast / Live Load
        if "live" in selected_cases:
            objects.append(self.Loc.LoadCase(
                no=2,
                name="Live Load",
                analysis_type=1,
                static_analysis_settings=1
            ))

        # Lastfall 3: Schnee
        if "snow" in selected_cases:
            objects.append(self.Loc.LoadCase(
                no=3,
                name="Snow Load",
                analysis_type=1,
                static_analysis_settings=1
            ))

        return objects

    def default_load_case(self):
        return self.create_load_cases(["sw"])
